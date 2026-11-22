# Distinguishing Type Access from Package Visibility in Java Modules

In Java, the question **“If a class is `public`, can it be used from elsewhere?”** cannot always be answered merely by looking at the class modifier. For an application organized into **named modules** under the **Java Platform Module System (JPMS)**, you must check both **type access** and **whether the package containing that type is exposed externally by the module**.

The three main conditions for code in **module A** to directly use a type from **module B** via ordinary Java syntax are:

1. **A reads B** (*module readability*), typically via `requires B;` in `module-info.java`.
2. **B exports the package containing the type to A**, typically via `exports package.name;` or `exports package.name to A;`.
3. **The type itself has appropriate access**, for example a top-level class needs to be `public` if used from another package; next, the constructor, field, and method being called must also have an appropriate access level.

If any condition is missing, the compiler may reject the call, **even though the class source code is written with `public`**.

Conceptual example:

```java
// In module library.core:
module library.core {
    exports library.api;
}
```

```java
// In package library.api:
package library.api;

public class Greeting {
    public String text() {
        return "Xin chào";
    }
}
```

```java
// In module app.main:
module app.main {
    requires library.core;
}
```

Code in module `app.main` can use `library.api.Greeting` because package `library.api` is exported, type `Greeting` is `public`, and module `app.main` reads `library.core`.

However, if module `library.core` **does not export** `library.api`, then `public class Greeting` **is not enough** to allow module `app.main` to import the type through normal compilation.

That is the core difference:

- **`public` on a type** answers: *Within the scopes where the type can be accessed, which code is allowed to use this type?*
- **`exports` on a module** answers: *Which packages are exposed for other modules to directly use their public types?*
- **`requires` on the consuming module** answers: *Can this module read the module providing the API?*

This lesson uses Java 17+ with file structures, compile/run commands, stdout, and easily confused scenarios involving `public`, package-private, `exports`, `opens`, and reflection.

## 1. Four Concepts to Keep Separate

| Concept | Declared at | Answers the question |
| --- | --- | --- |
| **Type access** | `public class Foo`, `class Foo`, nested type modifiers | Who is allowed to use the type name `Foo`? |
| **Member access** | `public Foo()`, `private int x`, `protected void m()`… | Who is allowed to call the corresponding constructor/field/method? |
| **Module readability** | `requires other.module;` and other module rules | Can the consuming module “read” the module containing the definition? |
| **Package export** | `exports some.package;`, `exports some.package to another.module;` | Which packages are allowed by the module to have their public APIs used from outside? |

For calling a constructor, you must also consider **matching signatures**, overloads, and the accessibility of that constructor itself. An exported package only makes **the public API of accessible types** available; it does not automatically expose all internal details.

### Layers of Checks

```text
Code in module app.client wants to use library.api.Greeting
                            |
                            v
          Does app.client read library.core?
                 /                     \
                No                     Yes
                |                        |
         Not accessible                  v
                            Does library.core export
                            library.api to app.client?
                                 /          \
                                No          Yes
                                |             |
                         Not accessible       v
                                   Is Greeting public
                                   and is the type accessible?
                                        /        \
                                       No        Yes
                                       |           |
                                Not accessible     v
                                      Is the member to call
                                      accessible?
                                         /       \
                                        No       Yes
                                        |          |
                                  Access error   The call may be
                                                 valid regarding access
```

The diagram only shows **accessibility conditions**. A program can still fail to compile due to wrong argument types, a non-existent constructor, importing the wrong name, an unsuitable classpath/module path, etc.

## 2. There Is No “`public` Modifier” for a Package

The syntax:

```java
package library.api;
```

only declares the **package name** to which the Java compilation unit belongs. A Java package itself **is not declared `public` or `private`** like a field or class.

Two independent operations:

1. In the type's Java file, choose the modifier, such as `public class Greeting` or `class Helper`.
2. In the named module's `module-info.java`, choose which packages are **exported**.

Example:

```java
module library.core {
    exports library.api;
}
```

The `exports library.api;` clause **does not change the modifiers of the types** in this package. If `library.api` has a package-private `class HiddenHelper`, that type remains package-private even though the package is exported.

**There is no syntax** `public package library.api;` to replace `exports`. `exports` is a **module directive**, not a class access modifier.

### A Package Does Not Automatically “Export All Subpackages”

`exports library.api;` applies to the **exact package `library.api`**.

It **does not implicitly export**:

- `library.api.internal`;
- `library.api.dto`;
- `library.api.impl`.

If you want to expose additional packages, declare `exports` for each corresponding package itself. Package names that share a common prefix are still **distinct packages**.

## 3. Two Access Levels for a Top-Level Class

For a regular **top-level class**, Java allows:

```java
public class PublicType {
}
```

or:

```java
class PackageType {
}
```

- `PublicType` is public.
- `PackageType` is **package-private** because it has no access modifier.
- A top-level class **cannot** be declared `private class PackageType` or `protected class PackageType`.
- The `private`/`protected` rules apply to nested member types and to fields/methods/constructors in appropriate contexts, not top-level classes.

A package-private class does not become public when a module exports the package containing it.

```java
package library.api;

class Helper {
    static String value() {
        return "Nội bộ";
    }
}
```

If the module containing the class declares `exports library.api;`, code in another package within a consuming module still **cannot** write:

```java
import library.api.Helper;  // Error: Helper is not public
```

There is no contradiction: **the package is exported**, but **type Helper does not have public access**.

## 4. Named Modules, `module-info.java`, and `requires`

An explicit named module is declared in `module-info.java`:

```java
module app.client {
    requires library.core;
}
```

Here:

- `app.client` is the name of the current module.
- `library.core` is the name of another module that the current module needs to read.
- `requires library.core;` establishes a **readability** relationship from `app.client` to `library.core` when the module graph is validly resolved.
- `requires` **does not** force `library.core` to export all packages to `app.client`.

A named module can **read module B** yet still not directly access public classes located in B's **unexported** packages.

### `java.base` Is a Special Case

Ordinary named modules implicitly read `java.base`, which provides foundational APIs such as `java.lang` and `java.util`. You usually **do not have to write**:

```java
requires java.base;
```

to use `String`, `Object`, or `ArrayList`.

`requires` is used for other named modules that your module directly depends on, or in special situations according to JPMS.

### Do Not Confuse Module Names with Package Names

`module library.core` is the **module** name. `package library.api` is the **package** name. The two names are not required to match.

A module can contain multiple packages:

```text
library.core (module)
├── library.api
├── library.internal
└── library.data
```

Each `exports` selects a single **package**, rather than automatically selecting the entire module or all names sharing a common prefix.

## 5. Complete Example: Module Exporting an API While Hiding an Internal Package

This is a **compilable/runnable Java 17** program illustrating the three layers: readable module, exported package, and public class.

### 5.1. Directory Structure

From a new working directory:

```text
src/
├── academy.lib/
│   ├── module-info.java
│   └── academy/
│       └── lib/
│           ├── api/
│           │   └── Greeting.java
│           └── internal/
│               └── SecretText.java
└── academy.app/
    ├── module-info.java
    └── academy/
        └── app/
            └── Main.java
```

### 5.2. The Library-Providing Module

**`src/academy.lib/module-info.java`**

```java
module academy.lib {
    exports academy.lib.api;
}
```

Only package `academy.lib.api` is exported. Package `academy.lib.internal` is not exported externally.

**`src/academy.lib/academy/lib/internal/SecretText.java`**

```java
package academy.lib.internal;

public final class SecretText {
    private SecretText() {
    }

    public static String suffix() {
        return " từ thư viện";
    }
}
```

**Note:** `SecretText` is a **public class** and the `suffix()` method is **public static**. Yet it resides in an **unexported package**. Therefore, being public **is not enough** to allow module `academy.app` to use it directly.

**`src/academy.lib/academy/lib/api/Greeting.java`**

```java
package academy.lib.api;

import academy.lib.internal.SecretText;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào " + name + SecretText.suffix();
    }
}
```

`Greeting` is a public class in an **exported package**. It is allowed to import `SecretText` from the internal package because both classes belong to the **same module `academy.lib`** and `SecretText` is public.

Not exporting `academy.lib.internal` **does not prevent code within module `academy.lib` itself from using public types of that package**.

### 5.3. The Consuming Module

**`src/academy.app/module-info.java`**

```java
module academy.app {
    requires academy.lib;
}
```

**`src/academy.app/academy/app/Main.java`**

```java
package academy.app;

import academy.lib.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("An"));

        // academy.lib.internal.SecretText.suffix();
        // INVALID if uncommented: package academy.lib.internal
        // is not exported by academy.lib to academy.app.
    }
}
```

### 5.4. Compiling and Running

From the directory containing `src`:

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m academy.lib,academy.app
java --module-path mods -m academy.app/academy.app.Main
```

**Exact stdout:**

```text
Xin chào An từ thư viện
```

Explanation of the result:
1. `academy.app` **reads** `academy.lib` via `requires academy.lib;`.
2. `academy.lib` **exports `academy.lib.api`**, so `academy.app` can see the public class `Greeting`.
3. `Greeting.message` runs internal library code, calling `SecretText.suffix` from an **unexported package** that is nevertheless **within the same module**, so it is valid.
4. `academy.app` is not permitted to directly import/call `SecretText` even though this type is public, because the package containing it is not exported externally.
5. The command `java --module-path mods -m academy.app/academy.app.Main` launches the main class of the named module `academy.app`.

This is a classic example of JPMS's goal: **intentionally exposing APIs while hiding implementation packages**.

## 6. What Happens If `requires` Is Missing?

In the example above, suppose you remove the line:

```java
requires academy.lib;
```

from `academy.app/module-info.java` while still keeping:

```java
import academy.lib.api.Greeting;
```

then module `academy.app` does not establish the required readability relationship to `academy.lib` in the ordinary module graph. Having `academy.lib.api` exported **does not automatically create readability** for every module.

An error usually relates to content like:

```text
package academy.lib.api is not visible
(module academy.app does not read module academy.lib)
```

The specific `javac` message may vary depending on the compilation command and how modules are resolved, but essentially it is **missing module readability**.

**How to fix:** keep `requires academy.lib;` in the consuming module, ensuring that module `academy.lib` is validly present on the module path and resolved.

Do not try to fix it by making `Greeting` `public` again: the class is already public, and the obstacle lies in **module readability**.

## 7. What If `requires` Is Present, but the Package Has No `exports`?

Keep:

```java
module academy.app {
    requires academy.lib;
}
```

but change the library module to:

```java
module academy.lib {
    // Do not export academy.lib.api;
}
```

In that case, `academy.app` **reads** `academy.lib`, but **is not allowed to directly use package `academy.lib.api`** from outside.

A typical error:

```text
package academy.lib.api is not visible
(package academy.lib.api is declared in module academy.lib,
 which does not export it)
```

**The right fix depends on the API contract:**

- If `academy.lib.api` is genuinely a public API: declare `exports academy.lib.api;`.
- If the package is intentionally internal: do not export it; instead, provide a public facade/interface in an exported package.
- If you want to open it **only to a few specific modules**, consider **qualified exports** (`exports ... to ...`).

**You should not** change all internal packages to exported just so a single isolated import can compile; doing so bloats the library's API surface.

## 8. An Exported Package Does Not Mean Every Type Is Public

Right inside package `academy.lib.api`, we can declare:

**`PublicEndpoint.java`**

```java
package academy.lib.api;

public class PublicEndpoint {
    public String name() {
        return InternalFormatter.format("An");
    }
}
```

**`InternalFormatter.java`**

```java
package academy.lib.api;

final class InternalFormatter {
    private InternalFormatter() {
    }

    static String format(String input) {
        return "[" + input + "]";
    }
}
```

Suppose the module containing both files has `exports academy.lib.api;`:

- Class `PublicEndpoint` is public, so callers outside the module can access it **if the module is readable**.
- Class `InternalFormatter` is **package-private**, so it **does not** become a public API type just because the package is exported.
- `PublicEndpoint` is allowed to call `InternalFormatter.format` because both classes are in the **same package** and in a valid context.
- Code in another package cannot import `academy.lib.api.InternalFormatter` directly.

The exact principle is: `exports` **makes public types and their validly accessible members** usable from permitted modules. It **does not** turn package-private types/members into public ones.

### Package-Private Differs from “Module-Internal”

Package-private means **package** scope, not module-wide scope.

If you have:

```java
package academy.lib.api;

class Helper {
}
```

then a class in **`academy.lib.internal`**, even though it is in the **same module**, still cannot use `Helper` directly like a top-level public class. Being in the same module satisfies **exports**, but **does not disable Java access modifiers**.

Two-way summary:

- **Public class in an unexported package:** code in a different package **within the same module** can use it if access rules are satisfied, but external modules cannot use it directly.
- **Package-private class in an exported package:** code in the **same package** can use it, but other modules cannot use it merely because the package is exported.

## 9. Member Access Is the Next Check Layer

Even when module `academy.app` reads `academy.lib`, the package is exported, and the class is public, you still need to check the **constructor, field, and method** being called.

Suppose:

```java
package academy.lib.api;

public class Customer {
    private final String id;
    int points;
    protected String group;

    private Customer(String id) {
        this.id = id;
        this.group = "DEFAULT";
    }

    public static Customer of(String id) {
        return new Customer(id);
    }

    public String id() {
        return id;
    }
}
```

From an independent class in another package belonging to a module that reads the API:

```java
Customer customer = Customer.of("C-1");
System.out.println(customer.id()); // C-1

// new Customer("C-1");     // INVALID: private constructor
// System.out.println(customer.points); // INVALID: package-private
// System.out.println(customer.group);  // INVALID if caller does not have
//                                        // a valid protected context
```

The module conditions have been met, yet each member is still subject to **Java access control**:

- A `private` constructor remains private.
- A package-private field remains open only to code in the corresponding package.
- `protected` still follows the special same-package and subclass rules.
- A `public` method is part of the public API if all outer access layers are valid.

**No `exports` clause turns `private Customer(...)` into a public constructor.**

## 10. `protected` Still Has Its Own Rules Across Modules

`exports` does not replace the access rules of `protected`.

Suppose a library exports package `core.api`:

```java
package core.api;

public class Base {
    protected int value = 1;

    protected Base() {
    }

    protected void increase() {
        value++;
    }

    public int getValue() {
        return value;
    }
}
```

A subclass in another module/package that **reads the library module** can:

```java
class Derived extends Base {
    Derived() {
        super();         // protected superclass constructor is valid
    }

    void update() {
        this.increase(); // protected instance method on this is valid
    }
}
```

However, outside the declaring package, **non-subclass code** cannot call `new Base()` merely because the module exports the package, and cannot use `otherBase.value`.

Even within a subclass outside the package, accessing a protected **instance member** via a receiver is also subject to type constraints; you cannot freely write `Base other; other.value` as you could when in the same package.

### Package-Level and Module-Level Access Do Not Replace Each Other

An easy way to remember:

- `exports` handles the **module gate** for the package.
- `protected` handles **member access rights** based on package/inheritance.
- `super(...)` handles **calling a valid superclass constructor**.
- The conditions for all three must be satisfied together.

## 11. Unqualified `exports` and Qualified Exports

JPMS supports two forms:

```java
exports catalog.api;
```

and:

```java
exports catalog.spi to catalog.plugin;
```

### `exports catalog.api;`

This is an **unqualified export**: package `catalog.api` is exported to **modules that read the providing module** in general, without restricting the list of target module names.

### `exports catalog.spi to catalog.plugin;`

This is a **qualified export**: package `catalog.spi` is exported only to the listed module, here `catalog.plugin`.

Another module such as `catalog.app` **cannot** directly use `catalog.spi` simply because it declares `requires catalog.core;`.

Things to note:

- A qualified export still requires the type being used to have an appropriate access modifier.
- The receiving module also needs **readability** to the module containing the package.
- A qualified export **is not equivalent to `opens`** for deep reflection.
- The `to` list can contain multiple permitted module names.

## 12. Complete Program: Qualified Export for a Partner Module

This example consists of **three named modules**, separate from the previous example.

### 12.1. File Structure

```text
src/
├── catalog.core/
│   ├── module-info.java
│   └── catalog/
│       ├── api/
│       │   └── Product.java
│       └── spi/
│           └── InternalPrice.java
├── catalog.plugin/
│   ├── module-info.java
│   └── catalog/
│       └── plugin/
│           └── PriceFormatter.java
└── catalog.app/
    ├── module-info.java
    └── catalog/
        └── app/
            └── Main.java
```

**`src/catalog.core/module-info.java`**

```java
module catalog.core {
    exports catalog.api;
    exports catalog.spi to catalog.plugin;
}
```

**`src/catalog.core/catalog/api/Product.java`**

```java
package catalog.api;

public final class Product {
    private final int price;

    public Product(int price) {
        this.price = price;
    }

    public int price() {
        return price;
    }
}
```

**`src/catalog.core/catalog/spi/InternalPrice.java`**

```java
package catalog.spi;

public final class InternalPrice {
    private InternalPrice() {
    }

    public static String format(int value) {
        return value + " VND";
    }
}
```

**`src/catalog.plugin/module-info.java`**

```java
module catalog.plugin {
    requires catalog.core;
    exports catalog.plugin;
}
```

**`src/catalog.plugin/catalog/plugin/PriceFormatter.java`**

```java
package catalog.plugin;

import catalog.api.Product;
import catalog.spi.InternalPrice;

public final class PriceFormatter {
    private PriceFormatter() {
    }

    public static String label(Product product) {
        return "Giá: " + InternalPrice.format(product.price());
    }
}
```

`catalog.plugin` can import `catalog.spi.InternalPrice` because the providing module specifies **`exports catalog.spi to catalog.plugin;`**, and the plugin declares `requires catalog.core;`.

**`src/catalog.app/module-info.java`**

```java
module catalog.app {
    requires catalog.core;
    requires catalog.plugin;
}
```

**`src/catalog.app/catalog/app/Main.java`**

```java
package catalog.app;

import catalog.api.Product;
import catalog.plugin.PriceFormatter;

public class Main {
    public static void main(String[] args) {
        Product book = new Product(120);
        System.out.println(PriceFormatter.label(book));

        // catalog.spi.InternalPrice.format(120);
        // INVALID if uncommented: catalog.core does not
        // export package catalog.spi to catalog.app.
    }
}
```

### 12.2. Compiling/Running

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m catalog.core,catalog.plugin,catalog.app
java --module-path mods -m catalog.app/catalog.app.Main
```

**Stdout:**

```text
Giá: 120 VND
```

Analysis:
1. `catalog.core` exports `catalog.api` to modules that read it, so `catalog.app` can use `Product`.
2. `catalog.core` exports `catalog.spi` only to `catalog.plugin`.
3. `catalog.plugin` can use `InternalPrice` to handle the delegated implementation part.
4. `catalog.app` only uses the `Product` and `PriceFormatter` APIs, and cannot directly import `InternalPrice`.
5. `PriceFormatter.label(Product)` is the public API of the plugin module, while how the plugin calls the internal SPI is a detail hidden from the app module.

**Benefit:** a library can collaborate with a specific partner module without exposing the entire SPI to all modules.

## 13. `opens` Differs from `exports`: Compile-Time API and Deep Reflection

A common point of confusion in Java 9+ is these two directives:

```java
exports demo.api;
opens demo.internal;
```

They are not synonymous.

| Criterion | `exports demo.api;` | `opens demo.internal;` |
| --- | --- | --- |
| Allows another module to directly import public types in source code? | **Yes**, if the module is readable and the type is public | **No**, not from `opens` alone |
| Accessing public members via reflection | Yes, subject to appropriate module/access conditions | Yes |
| Allows *deep reflection* such as attempting `setAccessible(true)` on a private member? | **No**, not from export alone | **Yes**, within the scope of opened modules/packages and runtime conditions |
| Primary stage of application | Access checks at compile time and runtime | Reflection at runtime |
| Has a form restricted to specific modules? | `exports p to m;` | `opens p to m;` |

### Important Point About Wording

`opens` does not create a “public import” from a hidden package. It **opens the package for reflection** within the permitted scope. Another module can use `Class.forName(...)` or a reflection-based framework, but source code **cannot simply `import` a type in an unexported package** just because it has `opens` on it.

In many framework applications (dependency injection, ORM, serialization), a package containing objects that need to be accessed by reflection can be given **opens** for the framework, while **not exported** as a public compile-time API.

### Qualified opens

```java
opens demo.entity to orm.framework;
```

grants reflection access under `opens` for package `demo.entity` to module `orm.framework`, **without opening it to every module**.

This is a way to narrow permissions compared to an unrestricted `opens demo.entity;`.

## 14. Runnable Example: `opens` for Reflection Without Exporting the Implementation

This example has two modules, independent from the previous examples.

### 14.1. Directories

```text
src/
├── vault.core/
│   ├── module-info.java
│   └── vault/
│       ├── api/
│       │   └── Factory.java
│       └── impl/
│           └── SecretBean.java
└── inspector.app/
    ├── module-info.java
    └── inspector/
        └── app/
            └── Main.java
```

**`src/vault.core/module-info.java`**

```java
module vault.core {
    exports vault.api;
    opens vault.impl to inspector.app;
}
```

**`src/vault.core/vault/impl/SecretBean.java`**

```java
package vault.impl;

public final class SecretBean {
    private final String secret;

    public SecretBean(String secret) {
        this.secret = secret;
    }
}
```

**`src/vault.core/vault/api/Factory.java`**

```java
package vault.api;

import vault.impl.SecretBean;

public final class Factory {
    private Factory() {
    }

    public static Object sample() {
        return new SecretBean("HIDDEN");
    }
}
```

**`src/inspector.app/module-info.java`**

```java
module inspector.app {
    requires vault.core;
}
```

**`src/inspector.app/inspector/app/Main.java`**

```java
package inspector.app;

import java.lang.reflect.Field;
import vault.api.Factory;

public class Main {
    public static void main(String[] args) throws Exception {
        Object bean = Factory.sample();
        Field field = bean.getClass().getDeclaredField("secret");
        field.setAccessible(true);
        System.out.println(field.get(bean));

        // import vault.impl.SecretBean; // INVALID access:
        // vault.impl is not exported.
    }
}
```

In the `Main.java` source, the commented `import ...` line is purely **illustrative**; if you want to actually test the import, the import must be placed in the declaration section at the top of the file, not inside the method.

### 14.2. Compiling/Running

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m vault.core,inspector.app
java --module-path mods -m inspector.app/inspector.app.Main
```

**Stdout:**

```text
HIDDEN
```

Why does this work?
1. Module `inspector.app` has `requires vault.core;` and package `vault.api` is exported, so the caller can use `Factory`.
2. `Factory.sample()` returns an actual instance of class `vault.impl.SecretBean`, but **the public return type is `Object`**.
3. `vault.impl` **is not exported**. Therefore `Main` cannot directly import `SecretBean` through the ordinary compile-time API.
4. `getDeclaredField("secret")` uses reflection to retrieve information about the private field.
5. `field.setAccessible(true)` is permitted in this case because `vault.core` declared **`opens vault.impl to inspector.app;`**.
6. `field.get(bean)` reads the value of the private field and prints `HIDDEN`.

If you remove the `opens vault.impl to inspector.app;` directive, `setAccessible(true)` in the example will no longer be allowed to bypass access checks for this private field, and may throw `java.lang.reflect.InaccessibleObjectException` under JPMS/JDK 17 rules.

**Limitation to be aware of:** reflection with `setAccessible` should not be used to bypass APIs arbitrarily. `opens` grants a significantly broad level of access to the receiving module; keep the scope to the necessary packages/modules and carefully consider trusted frameworks.

## 15. What Is an `open module`?

In addition to `opens package.name;`, JPMS has the form:

```java
open module application.entities {
    requires java.sql;
}
```

An **open module** in principle opens the packages contained in the module for **deep reflection** at runtime according to JPMS rules.

This **is not equivalent** to exporting all packages for source-code imports. Without appropriate `exports` declarations, code in other modules still does not automatically gain compile-time permission to use public types in those packages via ordinary imports.

**Syntax note:** inside an `open module` declaration, you do not use separate `opens` directives for individual packages as in a normal module; the open module itself is already a module-level declaration.

### Which Form Should You Use?

- `opens p to framework.module;`: a narrow choice, appropriate when only a specific framework needs reflection access to a package.
- `opens p;`: any module can perform deep reflection according to the opened semantics on that package.
- `open module ...`: broader; use only when your application design requires opening many packages and you understand the consequences.

Do not choose `open module` merely to make it “easy to compile”: it **does not fix exports conditions**, while also broadening reflection capabilities.

## 16. `requires transitive` and Readability Through Dependencies

Sometimes your API module exposes types belonging to another module as part of its public contract.

Conceptual example:

```java
module types.model {
    exports types.api;
}
```

```java
module facade.api {
    requires transitive types.model;
    exports facade.api;
}
```

```java
module consumer.app {
    requires facade.api;
}
```

`requires transitive types.model;` means that modules reading `facade.api` under the corresponding relationship can be granted the ability to **transitively read `types.model`**.

If `facade.api` contains:

```java
package facade.api;

public class Service {
    public types.api.Model getModel() {
        return new types.api.Model();
    }
}
```

then the type `types.api.Model` appears in the public signature. To allow callers of `facade.api` to conveniently use that API, `requires transitive types.model;` may be appropriate, **but `types.model` must still export `types.api`** so that code is permitted to access the public class in that package.

**Do not interpret `requires transitive` as re-exporting all packages**. It affects **readability**, whereas **exports** remains an independent decision of the module owning the package.

The illustration above assumes `types.api.Model` is a public class with an appropriate constructor; it explains dependencies rather than being a complete project with a file structure.

### What Is `requires static` For?

`requires static optional.module;` expresses a dependency required at compile time but not mandatory in the same way at runtime in relevant scenarios. It is useful for optional dependencies, annotations, or APIs that may not be used at runtime.

`requires static` **does not expose public types** of an unexported package. Do not use it to resolve visibility errors caused by a missing `exports`.

## 17. Why Can the Same Module Still Access Public Types in an Unexported Package?

This point helps you understand `exports` properly.

Suppose a module has the structure:

```text
service.engine
  ├── service.api
  ├── service.internal
  └── service.logic
```

and:

```java
module service.engine {
    exports service.api;
}
```

The `public` classes in `service.logic` can still import `public` classes in `service.internal`, because both are in the **same module** and satisfy type access rules.

`exports` is a boundary **between modules**, not a rule saying “all packages within a module are forbidden from seeing each other”.

However:
- A **package-private class** in `service.internal` still cannot be used directly by code in `service.logic` merely because they are in the same module.
- A **private member** remains private under Java rules.
- A public type in `service.internal` remains **hidden from external modules** if the package is not exported.

**Short conclusion:** *Same module* does not automatically relax the access modifier of a type/member; *exported package* does not automatically relax the access modifier of a type/member. They are two independent axes.

## 18. Package-Private, Same Package Name, and Module Boundaries

Before JPMS, many Java examples explained package-private as “other classes in the same package can access it”. In an application with named modules, you must also keep in mind that **a package is tied to its module context**.

Do not assume that putting the same declaration:

```java
package shared.api;
```

in two different named modules is a valid way to “bypass” package-private. **Split packages** between named modules participating in the same module graph can lead to compilation/module-resolution errors and are not a package-private collaboration pattern that JPMS is designed to support.

If two components belonging to different modules need to interact, expose a **public API** in an appropriate exported package, or use an interface/facade/service abstraction.

### A Package Is Not a Module

For example:
- Module `finance.core` has packages `finance.api`, `finance.internal`.
- Module `finance.app` has package `finance.app`.

There is no requirement that **a package name must start with the module name** for JPMS to work, although that organizational convention often improves readability.

More important advice is to avoid placing identically named packages into multiple named modules in a way that causes a split package conflict.

## 19. Classpath and Module Path: Why Older Programs May Not Hit `exports` Errors

Java 17 can still run applications using the **traditional classpath** model.

If you use the classpath without organizing the application into explicit named modules, many application checks are evaluated under the **unnamed module**. In a simple Java project:

```text
src/
├── library/
│   └── Greeting.java
└── app/
    └── Main.java
```

**`src/library/Greeting.java`**

```java
package library;

public class Greeting {
    public static String text() {
        return "Hello";
    }
}
```

**`src/app/Main.java`**

```java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

Compiling and running using the classpath:

```bash
javac -encoding UTF-8 -d out src/library/Greeting.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Hello
```

In this example **there is no `module-info.java`**, and you do not have to declare `exports library;` for `app.Main` to use `library.Greeting`. Java still checks `public`, package-private, private, and protected according to normal rules, but there is no explicit module `library.module` restricting `library` via `exports`.

### When Combining the Classpath with Named Modules

If a classpath application uses a named module library on the module path, **module resolution** and the library's **exports** still matter. You may need to configure `--add-modules` or other directives suited to the topology.

**Do not conclude that “the classpath always ignores all module boundaries.”** That is an overly broad rule of thumb and easily wrong when mixing unnamed/named/automatic modules.

## 20. Automatic Modules Differ from Explicit Named Modules

A plain JAR without `module-info.class`, when placed on the **module path**, can become an **automatic module** under JPMS rules.

Notable characteristics:
- It has a **module name** derived automatically or supplied via metadata such as `Automatic-Module-Name`.
- It has broadened readability/export behavior under automatic module rules to facilitate migration from the classpath.
- It **is not equivalent** to an explicit module with a `module-info.java` where you explicitly listed `exports`.

This explains why a library JAR on the module path may allow access to more packages than expected if it is acting as an **automatic module** rather than an **explicit named module**.

**When strict API encapsulation is needed**, you should verify which form the library is being loaded as, rather than just looking at the JAR name and assuming JPMS is blocking all access to internal packages.

### `Automatic-Module-Name` Is Not `exports`

The `Automatic-Module-Name` manifest attribute provides a stable module name for an automatic module, but **does not turn it into an explicit module with selective exports**. A library wanting precise control over exported packages needs an appropriate module descriptor.

## 21. `--add-exports` and `--add-opens`: Configuration Exceptions, Not Default API Design

Some systems migrating from older Java versions or using frameworks may require runtime/compile-time configuration to bypass module restrictions.

Common options:

```bash
--add-exports module.name/package.name=target.module
```

```bash
--add-opens module.name/package.name=target.module
```

General meaning:
- **`--add-exports`**: adjusts the ability to use public types in an otherwise unexported package for the specified target, in the appropriate tool context.
- **`--add-opens`**: adjusts the ability for reflective access to a package at runtime for the specified target, under the applicable rules.

The two options **are not equivalent**, and the exact syntax may vary depending on whether you are configuring `javac` or `java`, which consuming modules exist, as well as the `ALL-UNNAMED` target.

**Practical notes:**
1. Do not use these options as a default workaround for library APIs that you control.
2. Only open or export **packages that are genuinely needed** to appropriate modules.
3. `--add-opens` for reflection **does not fix source-level imports** of a public type in an unexported package.
4. `--add-exports` for public APIs **does not automatically allow access to private fields** via `setAccessible(true)` if the package has not been opened.

If you find yourself needing many `--add-exports` flags to access internal JDK packages such as `jdk.internal.*`, that is a sign to reconsider depending on unstable implementation details.

## 22. Access Control for Nested Types in an Exported Package

A public top-level class inside an exported package can contain multiple nested types with different access modifiers:

```java
package academy.lib.api;

public class Container {
    public static class PublicNested {
    }

    protected static class ProtectedNested {
    }

    static class PackageNested {
    }

    private static class PrivateNested {
    }
}
```

If the module has exported `academy.lib.api` to the caller, then:
- `Container` is a public top-level type.
- `Container.PublicNested` is a **public nested type**, which can be used from qualifying locations.
- `ProtectedNested` remains subject to protected rules.
- `PackageNested` remains package-private.
- `PrivateNested` remains private.

**Just because the package and outer class are public does not make every nested type public.** The access levels of nested types continue to be checked.

### Example of Dots in Type Names

`Container.PublicNested` is a **member type**, not a package named `Container`. Read the name structure accurately:
- `academy.lib.api` is the package;
- `Container` is the top-level class;
- `PublicNested` is the nested class.

`exports academy.lib.api;` selects the package, not individual nested types. Nested type access is determined by its Java declaration.

## 23. Exports Does Not Make a Public Class Instantiable If Its Constructor Is Private

A simple case:

```java
package academy.lib.api;

public final class Settings {
    private Settings() {
    }

    public static Settings create() {
        return new Settings();
    }
}
```

Suppose the library module exports `academy.lib.api`, and the client module has `requires academy.lib;`.

The caller **can**:

```java
Settings settings = Settings.create();
```

but **cannot**:

```java
Settings settings = new Settings();
```

because the `Settings()` constructor is private. No `exports` clause removes the access modifier restriction of this constructor.

This is commonly used for:
- Static factory methods;
- Utility classes;
- Controlled object lifecycle;
- Encapsulation or APIs that expose only specific ways to create objects.

`exports` resolves **module/package accessibility**; the constructor is still checked separately.

## 24. Does `exports` Affect Calling Public Methods in an Unexported Package?

Suppose:

```java
package academy.lib.internal;

public class InternalTool {
    public static String run() {
        return "OK";
    }
}
```

Even though both the class and the method are `public`, the client module cannot directly `import academy.lib.internal.InternalTool;` if `academy.lib.internal` is not exported to the client.

**A public method inside a public class in an unexported package does not automatically become a direct-call API from outside the module.**

However, code **within the same module** can use this class, as in the example where `academy.lib.api.Greeting` calls `SecretText`. If a public facade method in an exported package **handles calling** InternalTool and returns a `String`, the caller can use the **facade** according to the API contract.

That is the way to separate:
- **The exposed API surface** (exported packages).
- **Implementation details usable internally within the module** (unexported packages).

This separation typically lets you change the implementation without forcing client modules to change their imports or references to internal classes.

## 25. Reflection Context and Public Members of an Exported Package

`exports` affects reflection, but you must distinguish between **public reflection** and **deep reflection**.

With an unconditionally exported package, the client module can use reflection on the appropriate **public members of public types**, for example:

```java
Class<?> type = Class.forName("academy.lib.api.Greeting");
System.out.println(type.getName());
```

But if you want to access a **private field** using:

```java
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
```

then **`exports` alone does not automatically allow bypassing private access** of a named module. You need to check whether the module **opens** the package to the caller module.

Do not infer that a successful `Class.forName` call means you can invoke every constructor, read every private field, or bypass module encapsulation. Class loading, visibility, member accessibility, and reflective suppression of access checks are distinct layers of concern.

## 26. A Few Exceptions: JNI, Reflection, and Runtime Enforcement

Access rules in Java are largely enforced by the compiler when compiling source code, but the JVM/module system also enforces appropriate runtime constraints when linking/accessing types and members.

Therefore, avoid two overstated claims:

- **“Everything is checked only at compile time.”** Not true in all situations when executing bytecode, linking, and using reflection.
- **“`public` means anyone who has the class file can use everything.”** Not true when accounting for module exports/opens and member access rights.

A more accurate model:
- **Normal Java code:** the compiler analyzes types, module readability, exports, and access modifiers; the JVM still enforces the relevant boundaries.
- **Reflection:** accessibility is not completely identical to static import/call syntax; `exports` and `opens` play different roles.
- **Special/privileged mechanisms:** there are APIs and configurations that can adjust access, but that is no reason to neglect API design.

This lesson focuses on **the intended design model for Java 17**, rather than treating private, unexported packages, or opens as an absolute security boundary against malicious code running with high privileges.

## 27. Common Mistakes When Organizing a Project with JPMS

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Class is `public`, but cannot be imported from another module | The package containing the class is not exported to the client | Export the right API package or provide a facade |
| Package has `exports`, but a class still cannot be imported | That class is package-private | Make the class part of the public API if genuinely needed, or keep it internal |
| `requires library.core;` is present, yet package is still reported as not visible | Library does not export the right package / qualified export was not granted to the client | Check the library's `module-info.java` |
| Package is exported, yet compiler reports module does not read | Missing readability in the consuming module | Add `requires` or fix the module graph properly |
| `exports p;` is declared, yet `p.internal` is inaccessible | Export does not include subpackages | Export it separately if it is genuinely part of the API |
| `exports p to friend;` is declared, yet another app cannot import it | Qualified export is granted only to module friend | Do not bypass via import; design a public API or adjust the `to` list |
| `opens p;` is declared, yet `import p.Type` still fails | Opens is not exports for source-level APIs | Use exports if you genuinely want a public API |
| `exports p;` is declared, yet `setAccessible(true)` on a private field fails | Export does not grant deep reflection | Use qualified opens if a framework genuinely needs it |
| Public class in an exported package has a private constructor | Constructor is not accessible | Use an appropriate factory or public constructor |
| Public method in a package-private class cannot be called directly | Enclosing type is not public | Create a public facade/type in an exported package |
| Package-private method in another package cannot be called despite being in the same module | Being in the same module does not remove access modifiers | Use an appropriate public/protected API |
| Using `--add-exports` to expose a private field | Add-exports is not synonymous with opens | Distinguish public source access from deep reflection |
| Project works on classpath, but fails when moved to module path | Named modules add requires/exports and package conflicts | Design module descriptors and fix the module graph |
| Two named modules contain the same package, causing an error | Split packages | Reorganize package/module boundaries |
| `requires transitive` is used, yet the dependency's API type is still unusable | The dependency's package is not exported | The module owning the type must export the API package |
| Public type in module fails to expose its API properly | Wrong package name, wrong module name, or wrong source path | Check package paths and module source layout |
| Framework using reflection fails on Java 17 | Package containing entities/models is not opened to the framework | Grant narrow opens access according to the framework contract |
| Configuring modules solely because the package name matches the module name | Confusing package namespaces with modules | Check each `module-info.java` and actual packages |

## 28. Self-Practice Exercises with Answers

### Exercise 1 — Public Class, Unexported Package

Library:

```java
module demo.lib {
}
```

```java
package demo.api;

public class Hello {
    public static String text() {
        return "Hi";
    }
}
```

The app module has:

```java
module demo.app {
    requires demo.lib;
}
```

Can the app write `import demo.api.Hello;`?

**Answer:** **No**, because `demo.lib` has not exported `demo.api`. `public class Hello` only addresses the type's access level, not exposing the package across module boundaries. How to fix if you want to expose the API: add `exports demo.api;` to `demo.lib/module-info.java`.

### Exercise 2 — Exported Package, Package-Private Type

```java
module demo.lib {
    exports demo.api;
}
```

```java
package demo.api;

class Hidden {
}
```

The app module has `requires demo.lib;`. Can `demo.api.Hidden` be imported?

**Answer:** **No**. The package is exported, but the top-level class `Hidden` **is not public**. Changing exports does not change modifiers. If a public API is needed, the library designer must expose an appropriate public type.

### Exercise 3 — Are All Conditions Met to Use the Public API?

```java
module lib.one {
    exports lib.api;
}
```

```java
module app.one {
    requires lib.one;
}
```

```java
package lib.api;

public class Item {
    public Item() {
    }

    public String id() {
        return "A";
    }
}
```

Can a class `app.client.Main` in module `app.one` call `new Item()` after importing it?

**Answer:** **Yes**, provided the modules are compiled/resolved properly. The app reads `lib.one`, package `lib.api` is exported, class `Item` is public, and the no-arg constructor is public.

### Exercise 4 — Missing `requires` Despite Having `exports`

Module `lib.one` exports `lib.api`. Module `app.one` does not have `requires lib.one;`, yet its source imports `lib.api.Item`.

**Answer:** In the ordinary named modules model, **no**, because the client module does not yet have the required readability to `lib.one`. `exports` does not automatically replace `requires`.

### Exercise 5 — Qualified Export

```java
module company.core {
    exports company.spi to company.plugin;
}
```

Both `company.plugin` and `company.app` declare `requires company.core;`. Which module can directly use public types in `company.spi`?

**Answer:** `company.plugin` is granted the export; `company.app` **is not**. Public class/member conditions still have to be checked further in the plugin module.

### Exercise 6 — Does `opens` Replace `exports`?

```java
module entities {
    opens example.entity to orm.tool;
}
```

With `public class User` belonging to package `example.entity`, `orm.tool` already has the required readability relationship. Can the orm module simply write `import example.entity.User;` solely because of `opens`?

**Answer:** **No**. `opens` serves reflective access at runtime and does not grant permission to import public types for compile-time access. To use a Java source import, the package must be exported to the caller module.

### Exercise 7 — Public Class, Private Constructor

```java
package demo.api;

public final class Token {
    private Token() {
    }

    public static Token of() {
        return new Token();
    }
}
```

The module exports `demo.api`. The app requires the module. Can the caller invoke `new Token()`?

**Answer:** **No**, the constructor is private. `Token.of()` can be called and returns an instance. Exporting the package does not turn a private constructor into a public one.

### Exercise 8 — Nested Package Names

Does `exports com.example.api;` also export `com.example.api.internal`?

**Answer:** **No**. The two names are two distinct packages. If you genuinely want to allow clients to use the public API of the second package, you need a separate exports declaration; usually the `internal` package should be kept hidden and a facade provided.

### Exercise 9 — Same Module, Different Packages

`module demo.lib { exports demo.api; }` contains:
- `demo.api.PublicApi` is public;
- `demo.internal.Engine` is public;
- `demo.internal.Helper` is package-private.

Can `demo.api.PublicApi` use `demo.internal.Engine` and `demo.internal.Helper` directly?

**Answer:** It can use **`Engine`** because they are in the same module and the class is public; it cannot directly use **`Helper`** because it is package-private and in a different package. Not exporting `demo.internal` does not block module-internal code from using public types in this package.

### Exercise 10 — `requires transitive` Does Not Automatically Export

The facade module uses `requires transitive types.model;`. Module `types.model` contains a public class in an unexported package `types.internal`. Can the app module, which requires the facade, automatically import `types.internal.Secret`?

**Answer:** **No**. Transitive readability does not remove exports restrictions. The module owning the package still decides which packages form its public API.

### Exercise 11 — Configuring Reflection Access

A framework needs to read private fields in `company.entity` belonging to named module `company.data`. Should you add `exports company.entity;` or `opens company.entity to framework.module;`?

**Answer:** If the goal is **deep reflection**, consider **`opens company.entity to framework.module;`** according to the framework's contract. `exports` alone is not enough to access private members via `setAccessible(true)`. If the framework also needs to import public types at compile time, that is a **separate exports requirement** to evaluate additionally.

## 29. Checklist for Diagnosing Visibility Errors in Modules

1. **Determine whether the consuming code belongs to a named module.** Does it have a `module-info.java` and run on the module path?
2. **Identify the module containing the type being used.** Do not confuse package names with module names.
3. **Check readability:** does the caller module have `requires target.module;`, receive transitive readability, or have another valid readability relationship configured?
4. **Check exports:** is the package containing the type exported by the provider module to the caller module?
5. **Check qualified exports:** if `to module.name` is present, does the caller module match a listed name?
6. **Check public type:** does the top-level class/interface/record/enum used from outside the package have an appropriate access modifier?
7. **Check the member:** does the constructor, field, or method have an appropriate public/protected/package-private/private access level at the call site?
8. **Check the exact package:** exports for `a.b` do not automatically apply to `a.b.c`.
9. **Check the difference between opens and exports:** source imports require exports; deep reflection may require opens.
10. **Check the compile-time receiver type:** a runtime subclass method cannot automatically be called if the static type does not declare the member.
11. **Check the module source/module path structure:** are the directories, `module-info.java`, module names, and compiled class files set up properly?
12. **Check classpath/automatic modules:** how a library is loaded can change exports boundaries compared to an explicit module.
13. **Do not make everything public/exported:** expose only the packages and APIs that consumers genuinely need.
14. **Avoid depending on unexported packages:** instead of rampant `--add-exports`, prefer a facade or an API with a stable contract.
15. **When using a framework**, grant narrow qualified `opens` only to the needed packages when reflection is required; do not arbitrarily open the entire module.
16. **Run examples in a clean environment:** keep module fixtures separate, and use `javac --module-source-path` and `java --module-path` respectively when testing named modules.

## 30. Key Takeaways

- **`public` is the access level of a type**, whereas **`exports` decides which packages are exposed by a module** to other modules. They are **two independent layers**.
- The client module must normally **read the library module** via `requires` or a valid readability relationship, in addition to the `exports` condition.
- **A public class in an unexported package is still not a directly importable API** for other modules. Conversely, **an exported package does not turn a package-private class into a public one**.
- **Constructors/fields/methods are checked separately**: a public class in an exported package can still have a private constructor or a package-private method.
- **Qualified exports** (`exports p to m;`) only expose the package to the named module(s), not automatically to all consumers.
- **`opens` is for runtime reflection**, and is not equivalent to `exports` for source-level imports. Deep reflection into private members may require `opens`.
- **`requires transitive` affects readability**, and does not automatically export the dependency's packages.
- **Exporting does not include subpackages by name**, and being in the same module also does not bypass package-private/private access.
- In a Java 17 application, always check the **type**, **package**, **module readability**, **exports/opens**, and **member access** before concluding that a call is valid.
