# `exports` for Public APIs and `opens` for Reflection in Java 17

The Java Platform Module System (JPMS) allows an application to be divided into **named modules**, declare dependencies, and control which packages are accessible to other modules. Within a module, not every package automatically becomes an API for external modules.

Two important directives in `module-info.java` are:

- **`exports`**: exposes a package so other modules can use its accessible types and members under Java access rules.
- **`opens`**: allows other modules to perform deep reflective access into a package at runtime, including non-public members when access is appropriately enabled.

These two directives address different needs. `exports` serves normal source-code API usage and standard access; `opens` serves deep runtime reflection, commonly needed by serialization, dependency injection, or persistence frameworks. A package can be both exported and opened if the application genuinely requires both permissions.

## 1. Why Do Modules Need Package Control?

Before JPMS, a Java application was typically organized by packages and JARs. Packages group classes by namespace, but packages alone do not create a strong encapsulation boundary between JARs. Public classes on the classpath could generally be referenced by other code as long as the JAR was on the classpath.

JPMS adds boundaries at the module level. A module can:

- Declare a module name.
- Declare module dependencies with `requires`.
- Expose selected packages with `exports`.
- Open selected packages for reflection with `opens`.
- Declare services consumed or provided with `uses` and `provides`.

For example, a library module might contain:

```text
com.acme.library
├── com.acme.api
│   └── Greeter.java
└── com.acme.internal
    └── NameFormatter.java
```

The library wants consumers to call `Greeter`, while keeping `NameFormatter` as an implementation detail. The module descriptor can export the API package and omit exporting the internal package:

```java
module com.acme.library {
    exports com.acme.api;
}
```

As a result, other modules can use public types in `com.acme.api` if they read `com.acme.library`. Package `com.acme.internal` stays inside the module and is not exposed across the module boundary.

**Not exporting a package does not mean classes inside it must be private.** Classes can still be `public` for use by other classes within the same module; the module descriptor controls whether external modules can access that package.

## 2. `exports`: Exposing a Package to Other Modules' Source Code

Basic syntax:

```java
module com.acme.library {
    exports com.acme.api;
}
```

The `exports` directive exposes package `com.acme.api` to other modules. The consuming module still needs to declare its dependency using `requires`.

Client module example:

```java
module com.acme.client {
    requires com.acme.library;
}
```

A client class can import public types from the exported package:

```java
package com.acme.client;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Lan"));
    }
}
```

Two conditions to remember:

1. The client module must read the library module, typically via `requires com.acme.library;`.
2. The package containing the used type must be exported by the library module to the client module.

Without `requires`, the client module lacks the necessary readability relationship. Without `exports`, the package may exist in the library module but cannot be used by the client as a normal API.

### `exports` does not bypass Java modifiers

Exporting a package does not make all members `public`. Java language access rules still apply:

- Top-level package-private types still cannot be imported from another package.
- `private` members remain accessible only within the scope permitted by Java.
- Package-private members do not automatically become `public`.
- `protected` members still follow protected access rules, including inheritance requirements when accessed from another package.

`exports` opens a package at the module level; it does not erase class, field, constructor, or method access rules.

## 3. Complete Example: Export the API, Keep Internal Packages Hidden

Create the source layout for two modules:

```text
src/
├── com.acme.library/
│   ├── module-info.java
│   ├── com/acme/api/Greeter.java
│   └── com/acme/internal/NameFormatter.java
└── com.acme.client/
    ├── module-info.java
    └── com/acme/client/Main.java
```

### Library module

File `src/com.acme.library/module-info.java`:

```java
module com.acme.library {
    exports com.acme.api;
}
```

File `src/com.acme.library/com/acme/api/Greeter.java`:

```java
package com.acme.api;

import com.acme.internal.NameFormatter;

public class Greeter {

    public String greet(String name) {
        return "Hello, " + NameFormatter.format(name);
    }
}
```

File `src/com.acme.library/com/acme/internal/NameFormatter.java`:

```java
package com.acme.internal;

final class NameFormatter {

    private NameFormatter() {
    }

    static String format(String name) {
        if (name == null || name.isBlank()) {
            return "Guest";
        }

        return name.strip();
    }
}
```

`NameFormatter` does not need to be `public` because only `Greeter` in the same module uses it. Package `com.acme.internal` is not exported, so the client cannot import this internal class.

### Client module

File `src/com.acme.client/module-info.java`:

```java
module com.acme.client {
    requires com.acme.library;
}
```

File `src/com.acme.client/com/acme/client/Main.java`:

```java
package com.acme.client;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();

        System.out.println(greeter.greet("  Lan  "));
        System.out.println(greeter.greet(" "));
    }
}
```

Compile both modules from the project root directory:

```bash
javac --module-source-path src -d out -m com.acme.library,com.acme.client
```

Run the client module:

```bash
java --module-path out -m com.acme.client/com.acme.client.Main
```

Output:

```text
Hello, Lan
Hello, Guest
```

If you add `import com.acme.internal.NameFormatter;` to the client, the code will fail to compile because package `com.acme.internal` is not exported. This is the purpose of strong encapsulation: the library module exposes only the chosen API surface.

## 4. Qualified Exports: Exposing Only to Specified Modules

A library does not always want to export a package to all modules. You can use **qualified exports** to specify which modules are permitted access:

```java
module com.acme.library {
    exports com.acme.api to com.acme.client;
}
```

General syntax:

```java
exports package.name to module.one, module.two;
```

In the example above, package `com.acme.api` is exported only to module `com.acme.client`. Other modules, even if they have `requires com.acme.library;`, do not automatically get access to this package as a public API.

Qualified exports are useful when:

- A package is an internal API shared among specific modules within the same system.
- A library provides a package intended exclusively for an integration or adapter module.
- You want to narrow the public API surface in a large modular application.

This is still an export for normal access, not a mechanism for granting deep reflection permissions. If a framework in the specified module needs access to private members, `opens` must be considered separately.

## 5. `opens`: Opening a Package for Runtime Reflection

Reflection allows a program to inspect types, constructors, methods, and fields at runtime. For example, a framework might look up annotations, invoke constructors, or read fields to serialize an object into JSON.

In a strongly encapsulated module, knowing a class name does not mean having deep access to every member of that class.

The `opens` directive opens a package for **deep reflection at runtime**:

```java
module com.acme.model {
    opens com.acme.model.internal;
}
```

`opens com.acme.model.internal;` allows code in other modules to perform deep reflection on that package, subject to Java Reflection API rules.

You can restrict open access to a specific module:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.inspector;
}
```

This is a **qualified opens**. Only module `com.acme.inspector` is granted permission to open this package for deep reflection.

### `opens` does not make a package a source-level API

Another module cannot import classes in a package merely because that package is opened:

```java
// Module com.acme.inspector:
import com.acme.model.internal.Account; // Not allowed if package is not exported.
```

`opens` does not replace `exports`. It permits runtime reflective access, not using the package as a standard Java API at compile time.

This is the most important distinction:

| Directive | Purpose | Allows importing public types in package from another module? | Allows deep reflection into private members? |
| --- | --- | --- | --- |
| `exports` | Normal API access between modules. | Yes, if consumer reads source module and types/members satisfy Java modifiers. | Does not automatically grant deep reflection into private members. |
| `opens` | Deep reflection at runtime. | No. | Yes, for modules it is opened to and subject to reflection rules. |
| Both `exports` and `opens` | Exposes API and allows deep framework reflection. | Yes. | Yes. |

## 6. Reflection Example: Reading a Private Field from Another Module

Suppose a model module wants to keep an internal package unexported, while allowing an inspector module to read data via reflection.

Structure:

```text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/internal/Account.java
└── com.acme.inspector/
    ├── module-info.java
    └── com/acme/inspector/Main.java
```

### Model module

File `src/com.acme.model/module-info.java`:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.inspector;
}
```

File `src/com.acme.model/com/acme/model/internal/Account.java`:

```java
package com.acme.model.internal;

public class Account {

    private String token = "demo-token";

    public Account() {
    }
}
```

Package `com.acme.model.internal` is not exported. Clients cannot use `Account` as an API type in regular source code.

### Inspector module

File `src/com.acme.inspector/module-info.java`:

```java
module com.acme.inspector {
    requires com.acme.model;
}
```

File `src/com.acme.inspector/com/acme/inspector/Main.java`:

```java
package com.acme.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> accountType = Class.forName(
                "com.acme.model.internal.Account"
        );

        Constructor<?> constructor =
                accountType.getDeclaredConstructor();

        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access constructor via reflection"
            );
        }

        Object account = constructor.newInstance();

        Field tokenField = accountType.getDeclaredField("token");

        if (!tokenField.trySetAccessible()) {
            throw new IllegalStateException(
                    "Package is not opened for reflection"
            );
        }

        Object token = tokenField.get(account);

        System.out.println(token);
    }
}
```

Compile:

```bash
javac --module-source-path src -d out -m com.acme.model,com.acme.inspector
```

Run:

```bash
java --module-path out -m com.acme.inspector/com.acme.inspector.Main
```

Output:

```text
demo-token
```

Key points to note:

1. The inspector module does not import `Account`; it looks up the class by name at runtime.
2. Package `com.acme.model.internal` is specifically opened to `com.acme.inspector`.
3. `trySetAccessible()` requests reflective access. If permission is not granted, the method returns `false`.
4. Once access to the constructor and field is granted, reflection can instantiate the object and read the private field.

This example demonstrates the technical capability of reflection. Production applications should not expose private fields arbitrarily when a public API or well-designed accessor can be used instead.

## 7. `setAccessible`, `trySetAccessible`, and Strong Encapsulation Errors

The Reflection API provides methods to control access checks:

- `setAccessible(true)` requests bypassing Java access checks within permitted limits.
- `trySetAccessible()` attempts to enable access and returns `true` or `false` depending on eligibility.
- `canAccess(target)` checks whether the current instance already has access to the member.

In a module that does not open the package to the caller, trying to unlock a private member can fail. `setAccessible(true)` may throw `InaccessibleObjectException`; `trySetAccessible()` returns `false` when access cannot be enabled.

Example:

```java
Field field = accountType.getDeclaredField("token");

boolean accessible = field.trySetAccessible();

if (!accessible) {
    System.out.println("Deep access is not permitted");
}
```

If the package is opened to the module invoking reflection, `trySetAccessible()` can succeed. If the package is only exported and not opened, normal access to public APIs is allowed, but deep reflection into private members remains restricted.

Do not catch `InaccessibleObjectException` and ignore it as if the operation succeeded. Identify which module needs access, which package needs to be opened, and configure the descriptor with the proper scope.

## 8. `exports` and `opens` Can Both Apply to One Package

A package can both serve as a public API and require deep object access from a framework.

Example:

```java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.model to com.acme.json;
}
```

Here:

- `com.acme.domain.api` is exported for API consumer modules.
- `com.acme.domain.model` is opened to module `com.acme.json` so the JSON framework can perform deep reflection.

If the same package needs both permissions, both directives can be declared:

```java
module com.acme.domain {
    exports com.acme.domain.model;
    opens com.acme.domain.model to com.acme.json;
}
```

Consider whether the model package truly belongs in the public API. Many designs export only DTOs or stable APIs, and open a dedicated implementation package for frameworks.

Do not open an entire module just because one framework needs access to a couple of packages. Qualified opens helps minimize the reflection attack surface.

## 9. `open module`: Opening All Packages for Reflection

If a module declares:

```java
open module com.acme.application {
    exports com.acme.application.api;
}
```

then all packages in the module are opened for deep reflection at runtime. However, this **does not mean all packages are exported for source-level access**.

In an `open module`:

- Every package is opened for runtime reflection.
- Packages still require `exports` for other modules to import and use regular APIs.
- Additional standalone `opens` directives cannot be declared inside the body of an `open module`; the module already opens all packages.
- `exports` can still be used to expose APIs as needed.

Compare:

```java
module com.acme.application {
    opens com.acme.application.model;
}
```

Only package `com.acme.application.model` is opened.

```java
open module com.acme.application {
}
```

Every package of the module is opened for reflection.

Because `open module` grants broader access, use it only when a framework or runtime mechanism genuinely needs deep access across the entire module. In typical applications, opening specific packages to specific target modules is safer and clearer.

## 10. Frameworks Needing Reflection: Which Packages Should Be Opened?

Some frameworks need reflection to:

- Read fields and annotations.
- Invoke constructors, including non-public constructors.
- Assign values to fields or properties.
- Create proxies or perform injection.
- Map objects to database tables or JSON.

If the framework resides in its own module, packages containing processed classes may need to be opened to that framework module.

Application module example:

```java
module com.acme.app {
    requires com.acme.json;
    requires com.acme.persistence;

    exports com.acme.app.api;

    opens com.acme.app.dto to com.acme.json;
    opens com.acme.app.entity to com.acme.persistence;
}
```

Meaning:

- The API is exported for other modules to call.
- DTOs are opened to the JSON module.
- Entities are opened to the persistence module.
- Other internal packages remain closed.

Actual module names depend on the framework's module descriptor. Do not guess module names from Maven/Gradle artifact names; check the declared module name in the JAR (for example via `jar --describe-module`) or the framework's official documentation.

If the framework runs on the classpath in the unnamed module, qualified opens can target `ALL-UNNAMED`. However, use this only when compatibility with a non-modular framework is truly needed; for modular applications, prefer opening to specific named modules.

## 11. `ALL-UNNAMED` and Code on the Classpath

An application may combine named modules with libraries running on the classpath. Code on the classpath belongs to the **unnamed module** of the corresponding class loader.

In a module descriptor, qualified `opens` and `exports` target named modules. When temporary permission is needed for code in the unnamed module, the `--add-opens` command-line option can be used:

```bash
java --add-opens com.acme.model/com.acme.model.internal=ALL-UNNAMED \
     --module-path out \
     -m com.acme.inspector/com.acme.inspector.Main
```

This option opens package `com.acme.model.internal` of module `com.acme.model` to code in the unnamed module at runtime.

To open a package to a specific named module via command line:

```bash
java --add-opens com.acme.model/com.acme.model.internal=com.acme.inspector \
     --module-path out \
     -m com.acme.inspector/com.acme.inspector.Main
```

`--add-opens` is a runtime option. It does not make a package an API that can be imported at compile time.

Similarly, `--add-exports` adds export access for a package to a target module. This option can be useful when integrating or diagnosing legacy applications, but should not be used to mask a poorly designed module descriptor.

## 12. Distinguishing `--add-exports` and `--add-opens`

Two command-line options have similar names but different purposes:

| Option | Phase | Purpose |
| --- | --- | --- |
| `--add-exports sourceModule/package=targetModule` | Can be used at compile time and runtime. | Adds package export permission for the target module, enabling normal API access. |
| `--add-opens sourceModule/package=targetModule` | Runtime. | Adds package open permission for deep reflection. |

For example:

```bash
javac --add-exports com.acme.model/com.acme.model.api=com.acme.client ...
```

is an additional export permission for compilation (and at runtime the corresponding permission is also needed if the application relies on that export).

Whereas:

```bash
java --add-opens com.acme.model/com.acme.model.internal=com.acme.inspector ...
```

is a runtime package open permission for deep reflection.

Do not confuse `--add-opens` with `--add-exports`: a package opened for reflection does not automatically become a package exported for source code.

## 13. `requires`, `exports`, and `opens` Are Three Distinct Things

A common mistake is thinking `exports` alone allows a consumer module to access a package. In fact, JPMS separates three concepts:

- **Readability:** whether the consumer module reads the providing module, typically declared via `requires`.
- **Export:** whether the package is exposed for normal access.
- **Open:** whether the package is opened for deep reflection at runtime.

Example:

```java
// Module com.acme.library
module com.acme.library {
    exports com.acme.api;
}
```

```java
// Module com.acme.client
module com.acme.client {
    requires com.acme.library;
}
```

`com.acme.client` reads `com.acme.library` and is allowed to access package `com.acme.api` because that package is exported. If a framework in `com.acme.json` needs to read private fields in package `com.acme.model`, the library module needs to add the appropriate `opens`.

You can summarize this in a table:

| Directive | Answers the question |
| --- | --- |
| `requires` | Which modules does my module depend on / read? |
| `exports` | Which packages may other modules use as normal APIs? |
| `opens` | Which modules may perform deep reflection into which packages at runtime? |

## 14. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `package ... is not visible` | Consumer module does not read source module or package is not exported. | Check `requires` and `exports`. |
| `module ... does not read ...` | Missing readability relationship. | Add the appropriate `requires` to the consumer module. |
| `package ... is declared in module ..., which does not export it` | Package exists but is not exported to the module using it. | Export the public package or design the API through an exported package. |
| Class can be imported but member cannot be called | Java modifiers on class/member disallow access. | Check `public`, `protected`, package-private, and `private`. `exports` does not remove these rules. |
| `trySetAccessible()` returns `false` | Package is not opened to the module calling reflection or access conditions are unmet. | Add `opens package to caller.module;` if deep reflection is genuinely needed. |
| `InaccessibleObjectException` | Code attempted to enable deep access, but the module does not open the package. | Open the specific package to the target module or use a public API. |
| Framework cannot read private fields | Package containing models/entities has not been opened to the framework module. | Use qualified `opens` with the exact framework module name. |
| `opens` declared but import still fails | `opens` only grants runtime reflection permission, not compile-time source export. | Add `exports` if source access is needed; keep `opens` for reflection if needed. |
| Qualified opens has no effect on a classpath framework | Actual target is the unnamed module, not the specified named module. | Check how the framework is launched; consider `ALL-UNNAMED` if appropriate. |
| Entire module opened but package import still fails | `open module` opens for reflection, not exporting every package. | Declare `exports` for packages intended as APIs. |

## 15. Safe Module Design Principles

When designing modules for a Java 17 application, clearly separate which packages are APIs and which exist solely for implementation.

### Export only stable APIs

Choose packages containing types and contracts that other modules genuinely need. Avoid exporting all internal packages just to resolve compiler errors. Every exported package becomes part of the API surface that other modules can depend on.

### Open only to frameworks that need it

If a framework only needs reflection on entities, open the entity package to that framework module. Do not open an entire module when only one package needs access.

### Prefer qualified directives

If the specific consumer or framework module is known, use the qualified form:

```java
module com.acme.domain {
    exports com.acme.domain.api to com.acme.application;

    opens com.acme.domain.entity to com.acme.persistence;
}
```

This scopes access according to intent.

### Prefer public APIs over deep reflection when possible

If another module only needs to read data, a public accessor or dedicated API can be clearer and more durable than exposing private fields. Deep reflection suits frameworks or tools requiring generic mechanisms, but should not become the default way modules communicate.

### Do not open private state just for debugging convenience

Opening a package for reflection can allow the target module to read or mutate internal state. Grant permission only for a clear reason, and consider sensitive data held in those entities or objects.

## 16. Workflow for Choosing Between exports and opens

When another module needs access to a package, first identify the access pattern:

```text
Does another module need to use the package?
             |
             v
     Imports classes in source?
             |
       +-----+-----+
       |           |
      Yes          No
       |           |
       v           v
    requires?   Uses reflection?
       |           |
       v           v
    exports?    Deep reflection?
       |           |
       v       +---+---+
 Normal API    |       |
              Yes      No
               |       |
               v       v
             opens   Check normal
             package reflection permissions
```

- If another module needs to import types and call public APIs, readability and `exports` are required.
- If a framework needs access to private fields or constructors via reflection, `opens` to the framework module is required.
- If both are needed, declare both `exports` and `opens` scoped by package and target module.
- If a package is only used internally within the same module, neither export nor open is typically needed.

## 17. Quick Reference

| Need | Directive/configuration |
| --- | --- |
| Expose package to all modules reading current module | `exports com.acme.api;` |
| Export only to specific modules | `exports com.acme.api to com.acme.client;` |
| Open package for deep reflection from any module | `opens com.acme.model;` |
| Open only to a specific reflecting module | `opens com.acme.model to com.acme.inspector;` |
| Open all packages of a module for reflection | `open module com.acme.model { ... }` |
| Consumer module depends on library module | `requires com.acme.library;` |
| Open package at runtime via command line | `--add-opens source/package=target` |
| Add export via command line | `--add-exports source/package=target` |
| Inspect module name inside a JAR | `jar --describe-module --file library.jar` |

**Core principle:** `exports` exposes a package for normal API usage by other modules; `opens` grants runtime deep reflection permission. `requires` establishes readability, while Java modifiers still govern access to individual classes and members. Export only the packages intended as APIs, open only the required packages to the right frameworks, and avoid granting broader permissions than necessary.
