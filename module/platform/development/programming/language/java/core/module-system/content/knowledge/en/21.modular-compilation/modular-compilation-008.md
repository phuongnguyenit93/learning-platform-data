# Compile Errors Due to Missing requires or exports

## 1. Two Boundaries to Distinguish in JPMS

When compiling a modular application, Java checks both **module readability** and **package accessibility**. These two mechanisms are related, yet they answer two different questions:

- `requires` determines which modules the current module reads. If module A needs to use a type located in module B, A generally must declare `requires B`.
- `exports` determines which packages of a module can be accessed by other modules. Even if A reads B, A still cannot use a package of B if that package is not exported to A.

Therefore, a dependency may already be on the module path, yet the source still fails to compile due to a missing `requires`, or the module is already read, yet the package containing the needed type has not been exported.

Example:

```text
com.acme.app  --requires-->  com.acme.api
                                  |
                                  +-- exports com.acme.api
```

To use the public type `com.acme.api.Customer`, the consumer must read the `com.acme.api` module and the `com.acme.api` package must be exported.

## 2. Example API Module and Consumer

Source structure:

```text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

API module:

```java
module com.acme.api {
    exports com.acme.api;
}
```

Class in the exported package:

```java
package com.acme.api;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

Consumer module:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Consumer using the API:

```java
package com.acme.app;

import com.acme.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Ada");
        System.out.println(customer.name());
    }
}
```

Here, both conditions are met:

1. `com.acme.app` reads `com.acme.api` via `requires`.
2. `com.acme.api` exposes the `com.acme.api` package via `exports`.

## 3. Missing requires Error: Module Does Not Read Dependency

Suppose the consumer's module descriptor omits the directive:

```java
module com.acme.app {
    // Missing: requires com.acme.api;
}
```

Even though `com.acme.api` is on the module path and has exported its package, the consumer still does not read that module. When compiling the line:

```java
import com.acme.api.Customer;
```

The compiler may report:

```text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
but module com.acme.app does not read it)
```

The fix is to add the dependency to the consumer's `module-info.java`:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Do not modify the API module to export more packages when the error message clearly states that the consumer does not read the module. This is a readability error, controlled from the side of the module that needs to use the dependency.

### Distinguishing the module not found Error

If the consumer already has:

```java
requires com.acme.api;
```

but the compiler reports:

```text
module not found: com.acme.api
```

then the module descriptor already requested the dependency, but the compiler cannot locate the corresponding module. Check:

- Does the JAR or module directory actually exist?
- Does the module path point to the right directory containing the module?
- Does the module name in `requires` match the name declared in `module-info.java` or the module name derived from the JAR?
- Was the dependency mistakenly placed on the classpath instead of the module path?

Example of compiling when the API has already been packaged in the `mods` directory:

```bash
javac --module-path mods \
  --module-source-path src \
  -d out \
  -m com.acme.app
```

## 4. Missing exports Error: Module Is Read but Package Is Encapsulated

Suppose the API module has the descriptor:

```java
module com.acme.api {
    // Missing: exports com.acme.api;
}
```

The consumer still declares correctly:

```java
module com.acme.app {
    requires com.acme.api;
}
```

However, when importing `com.acme.api.Customer`, the compiler may report that the package is declared in module `com.acme.api` but that module does not export the package.

The fix is to export the right package in the module that owns the API:

```java
module com.acme.api {
    exports com.acme.api;
}
```

`exports` is a directive of the module containing the package. A consumer cannot export a package belonging to another module by adding a line to its own module descriptor.

Also remember that exporting a package does not mean every member is public. Consumers can still only access types and members according to standard Java access rules; package-private members do not become public.

## 5. Qualified exports: Exporting Only to Selected Modules

A module can restrict a package to only specific consumers:

```java
module com.acme.api {
    exports com.acme.api to com.acme.app;
}
```

This is a **qualified export**. The `com.acme.api` package is exported only to the named `com.acme.app` module. Other modules may read `com.acme.api`, yet still cannot access that package.

If a new consumer is `com.acme.report`, you need to consider adding this module to the list:

```java
module com.acme.api {
    exports com.acme.api to
        com.acme.app,
        com.acme.report;
}
```

Only use qualified exports when you genuinely want to restrict the set of consumers. If the package is a public API for all modules, use an unqualified export:

```java
exports com.acme.api;
```

Names in a qualified export list must be module names, not package names, arbitrary artifact names, or class names.

## 6. requires transitive: When a Public API Exposes a Dependency

Sometimes an intermediate module uses a type from a dependency in its own public API. In that case, consumers of the intermediate module may need to read that dependency.

Example:

```text
com.acme.app
    |
    | requires
    v
com.acme.facade
    |
    | requires
    v
com.acme.api
```

Suppose a public method on the facade returns `com.acme.api.Customer`:

```java
package com.acme.facade;

import com.acme.api.Customer;

public class CustomerFacade {
    public Customer findCustomer(String id) {
        // Implementation omitted
        return null;
    }
}
```

If the facade's descriptor only declares:

```java
module com.acme.facade {
    requires com.acme.api;
    exports com.acme.facade;
}
```

then the `com.acme.app` module declaring `requires com.acme.facade` does not automatically read `com.acme.api`. When the consumer needs to call `findCustomer` and use the `Customer` return type, the compiler may report that the dependency is not read or the package is not visible.

If the facade intentionally puts types from the API dependency into its public API and wants to propagate readability to consumers, use:

```java
module com.acme.facade {
    requires transitive com.acme.api;
    exports com.acme.facade;
}
```

`requires transitive` causes modules that read the facade to also read the API module. This is a decision about the facade's public contract, not a default fix for every `requires` error. If a consumer directly uses a dependency that is not intentionally re-exported by the facade, the consumer should declare `requires` for that dependency.

## 7. requires static and Optional Dependencies

The directive:

```java
requires static com.acme.annotations;
```

declares a dependency required at compile time that may be optional at runtime according to the rules of `requires static`. It is commonly suited for annotations or compile-time-only dependencies.

`requires static` is not a substitute for regular `requires` when the application actually needs the module at runtime. Nor can it be used to hide a missing module on the module path during compilation: the compiler still needs to locate that compile-time dependency.

## 8. exports and opens Are Not the Same

These two directives are often confused:

- `exports package.name;` allows other modules to access public types and public/protected APIs in the package according to Java access rules.
- `opens package.name;` allows deep reflective access to the package at runtime, for example when a framework needs to read or modify private members via reflection.

If an error occurs while compiling an import or type reference, check `requires` and `exports`. Adding `opens` usually will not fix a compile error caused by an unexported package.

Example of opening a package to a framework:

```java
module com.acme.model {
    exports com.acme.model.api;

    opens com.acme.model.internal to com.acme.framework;
}
```

The API package is exported so other code can compile against and call the public API. The internal package only opens reflective access to the specified framework.

## 9. Modular Compilation and Reading Error Messages

When compiling multiple modules from a source tree:

```bash
javac --module-source-path src \
  -d out \
  -m com.acme.api,com.acme.app
```

When compiling a consumer and taking dependencies from a built JAR/module directory:

```bash
javac --module-path mods \
  --module-source-path src \
  -d out \
  -m com.acme.app
```

You can run the application:

```bash
java --module-path out:mods \
  -m com.acme.app/com.acme.app.Main
```

On Windows, the separator between multiple entries in the module path is a semicolon (`;`) instead of a colon (`:`).

When reading compiler output, classify the message before fixing:

| Message or Symptom | Common Cause | Resolution |
|---|---|---|
| `module not found: X` | Module X cannot be found | Check the module path, module name, and artifact |
| Package is not visible because current module does not read module X | Missing readability | Add `requires X` in the consumer |
| Package is declared in module X, which does not export it | Package has not been exported | Add `exports` in the module owning the package |
| Package is not exported to module Y | Qualified export does not include the consumer | Update the target module list or use an unqualified export |
| Public API uses types from another module but consumer cannot read that module | Dependency is not propagated through the API module | Consumer adds `requires` or the API module uses `requires transitive` if appropriate |
| Reflection blocked at runtime | Package has not been opened for reflective access | Use `opens` or `--add-opens` for the appropriate situation |

Exact message wording may vary by JDK version and error site. Rely on the compiler's full explanation, especially the name of the module owning the package and the name of the module being compiled.

## 10. Short Diagnostic Workflow

When encountering a compile error in a modular project, follow this order:

1. Identify which package and module the imported type belongs to. You can inspect the descriptor with `jar --describe-module --file dependency.jar`.
2. Confirm the dependency module is on the module path of the `javac` command.
3. Check whether the consumer module declares `requires` for the right module.
4. Check whether the module owning the package has `exports` for that package to the consumer; if it is a qualified export, verify the exact module name.
5. If the type appears in an intermediate module's public API, consider `requires transitive`.
6. If the issue only occurs when a framework accesses private members at runtime, check `opens` rather than confusing it with a compile-time error.
7. Recompile all related modules using the same module path configuration to avoid using stale artifacts.

You can use `jdeps --check` to inspect a module's descriptor and dependencies:

```bash
jdeps --check com.acme.app --module-path mods
```

## Key Takeaways

- `requires` establishes readability between modules.
- `exports` exposes a package from the module that owns the package.
- Being able to read a module does not mean every package in that module is accessible.
- `requires transitive` propagates readability through an intermediate module when its public API demands it.
- `requires static` is a compile-time dependency that is optional at runtime, not a way to skip a dependency during compilation.
- `opens` serves reflective access at runtime; it does not replace `exports` for compile-time access.
