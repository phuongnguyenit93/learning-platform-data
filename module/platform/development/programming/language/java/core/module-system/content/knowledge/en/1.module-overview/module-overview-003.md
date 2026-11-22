# How modules enable encapsulation, dependencies, and package hiding

The Java Platform Module System (JPMS), introduced in Java 9, adds an organizational boundary at the **module** level. A module groups related packages, declares which modules it needs, and specifies which packages are exposed to other modules. As a result, an application can describe its dependencies explicitly and keep implementation packages internal.

The three main ideas to connect together are: **encapsulation** determines which code belongs to which module; **dependencies** determine which module is allowed to read and use another module; **package hiding** determines which parts of a module become external API and which parts are for internal use only.

## 1. Why does Java need module boundaries?

A Java application typically has many packages. Packages help group classes and interfaces by functionality while supporting access control through modifiers such as `public`, `protected`, package-private, and `private`.

However, packages alone do not fully express the dependency structure of an entire application. When using only the classpath, libraries can be discovered without an explicit module declaration stating which component depends on which component. `public` types in public packages can also end up with a broader usage surface than intended.

JPMS introduces a higher level of organization:

- **Package** groups related Java types.
- **Module** groups one or more packages and has a module name.
- **Module descriptor** declares the module name, dependencies, and packages exported externally.
- **Module path** is where Java searches for modules when compiling or running a modular application.

A named module usually has a `module-info.java` file at the root of the module's source code. When compiled, this file becomes `module-info.class` in the compiled module; when packaged into a modular JAR, the descriptor is placed at the root of the JAR.

Modules do not replace packages. Packages still organize classes inside a module; modules establish dependency and accessibility boundaries between groups of packages.

## 2. The module descriptor describes boundaries

Example of a module named `com.acme.model`:

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

This declaration means:

- The module name is `com.acme.model`.
- The module can contain multiple packages.
- The `com.acme.model.api` package is exported so other modules can use public types in that package.
- Other packages of the module do not automatically become external API.

Module names typically use reverse domain name notation to reduce name collisions, such as `com.acme.model`. This is a naming convention; it does not mean a module name is required to match a package name.

A module can declare multiple packages using multiple `exports` directives. If no `exports` declaration is provided for a package, other modules cannot access it in the ordinary way at compile time.

Every module implicitly reads the foundational `java.base` module. Therefore, descriptors do not need to write `requires java.base;` in ordinary examples.

## 3. Encapsulation: grouping what belongs to the same module

Suppose a customer management system has three parts:

- `com.acme.model`: customer data model.
- `com.acme.service`: customer lookup business logic.
- `com.acme.app`: launcher program and command-line interface.

The source code structure can look like this:

```text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/api/
│       └── Customer.java
├── com.acme.service/
│   ├── module-info.java
│   ├── com/acme/service/api/
│   │   └── CustomerService.java
│   └── com/acme/service/internal/
│       └── CustomerRepository.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/
        └── Main.java
```

Each direct subdirectory of `src` is a source module. Inside a module, directories continue to represent the package structure.

The `com.acme.service` module contains both `api` and `internal`. Both packages belong to the same module, so code within the module can collaborate using them according to Java access rules. Only the `api` package is exported; the `internal` package is an implementation detail.

Module-level encapsulation helps readers recognize which parts belong to the same component, while allowing that component to be built and distributed as a separate module. A modular JAR can contain the module's packages together with its descriptor.

## 4. Declaring dependencies with `requires`

A module can only use modules that it reads. The `requires` directive declares a direct dependency:

```java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
```

Here, `com.acme.service` needs `com.acme.model`. At compile time and runtime, Java must find the required module in the module graph. If a mandatory dependency cannot be found or a module cannot be resolved, the application cannot start under that configuration.

Two concepts must be distinguished:

- `import` in a Java file allows writing shorter type names, such as `import com.acme.model.api.Customer;`.
- `requires` in `module-info.java` declares the dependency and readability relationship between modules.

An `import` statement does not by itself create a module dependency. To use a type from another module, the current module must be able to read the module containing that type and the package containing the type must be appropriately exported.

### `requires transitive`

If a type from module A appears in the public API of module B, module C using B may need to read A to work with that API. In that case, B can declare:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

`requires transitive` means a module reading `com.acme.service` is also granted readability to `com.acme.model`. Only use it when that dependency is genuinely part of the API that the module intends to provide to consumers.

Related directives:

| Directive | Meaning |
|---|---|
| `requires module.name;` | Declares a direct mandatory dependency |
| `requires transitive module.name;` | Declares a dependency and propagates readability of the dependency module to modules that read the current module |
| `requires static module.name;` | A dependency required at compile time that may be absent at runtime |

You should not add `transitive` to every dependency. If a library is only used inside the implementation and does not appear in the public API, plain `requires` usually expresses the intent more clearly.

## 5. Hiding packages with `exports`

An important point of JPMS is that a package is not automatically public just because it contains a `public` class.

For example, the `com.acme.service` module exports only its API package:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

The module can contain two packages:

```text
com.acme.service.api
    CustomerService.java

com.acme.service.internal
    CustomerRepository.java
```

`public` types in `com.acme.service.api` can be used by other modules because this package is exported. Types in `com.acme.service.internal` remain inside the module boundary, even if a class in it is declared `public`.

Example:

```java
package com.acme.service.internal;

public class CustomerRepository {
    // Internal data access details of the service.
}
```

An external module cannot import and use `CustomerRepository` merely because the class has the `public` modifier. The package containing the class has not been exported from the module.

Three distinct layers of access control should be remembered:

1. **Module export:** whether other modules are allowed to access the package.
2. **Package and class access:** within an exported package, Java modifiers still determine which types and members are accessible.
3. **Object access:** `private`, `protected`, and member access rules remain in effect as usual.

Therefore, `exports` does not make every member `public`; it opens the package at the module boundary, after which Java's access rules continue to apply.

A package can be exported to a specific module using a qualified export:

```java
exports com.acme.service.internal to com.acme.test;
```

In that case, the package is exported restrictively to the `com.acme.test` module, rather than publicly to every module that can read the current module. This approach is useful when an integration or test module needs access to a special API.

## 6. `opens`: allowing deep reflection access

`exports` serves compile-time API accessibility and normal type usage. Some frameworks, however, need reflection to inspect or access non-public members, such as object-mapping frameworks, dependency injection, or serialization libraries.

For that case, JPMS provides `opens`:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to com.acme.mapper;
}
```

The `opens` directive allows the `com.acme.mapper` module deep reflective access to the `com.acme.model.internal` package, within the bounds of Java's reflection and access rules.

The two directives have different purposes:

| Directive | Purpose | Use when |
|---|---|---|
| `exports` | Allows other modules to use public types in the package | The package is an API the module wants to provide |
| `opens` | Allows deep reflective access at runtime | A framework needs to read or access members via reflection |

You can use `opens package.name;` to open a package for reflection from other modules. If written as `opens package.name to framework.module;`, the open permission is restricted to the named module.

The `open module` syntax opens all packages of the module for deep reflection:

```java
open module com.acme.legacy {
    requires com.acme.model;
}
```

`open module` is not equivalent to exporting all packages like `exports`. It serves reflection; other modules still do not get public API packages to import internal types in the ordinary way.

Open only the exact packages and exact modules needed. Opening an entire module can diminish the encapsulation benefits that JPMS brings.

## 7. Complete example with three modules

The files below combine dependencies, public APIs, and internal packages.

**Module `com.acme.model`:**

`src/com.acme.model/module-info.java`

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

`src/com.acme.model/com/acme/model/api/Customer.java`

```java
package com.acme.model.api;

public record Customer(String id, String name) {}
```

The model module exports only the `com.acme.model.api` package.

**Module `com.acme.service`:**

`src/com.acme.service/module-info.java`

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

`src/com.acme.service/com/acme/service/internal/CustomerRepository.java`

```java
package com.acme.service.internal;

import com.acme.model.api.Customer;

public class CustomerRepository {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }
}
```

`src/com.acme.service/com/acme/service/api/CustomerService.java`

```java
package com.acme.service.api;

import com.acme.model.api.Customer;
import com.acme.service.internal.CustomerRepository;

public class CustomerService {
    private final CustomerRepository repository =
            new CustomerRepository();

    public Customer find(String id) {
        return repository.findById(id);
    }
}
```

Service needs model to construct and return `Customer`. Because `Customer` appears in the return type of the `CustomerService.find` API, the descriptor uses `requires transitive` so that modules using service can read model through service.

The `com.acme.service.internal` package is not exported. `CustomerService` in the same module can still use `CustomerRepository`, while external modules cannot import the repository directly.

**Module `com.acme.app`:**

`src/com.acme.app/module-info.java`

```java
module com.acme.app {
    requires com.acme.service;
}
```

`src/com.acme.app/com/acme/app/Main.java`

```java
package com.acme.app;

import com.acme.model.api.Customer;
import com.acme.service.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        Customer customer = new CustomerService().find("C01");
        System.out.println(customer.id() + " - " + customer.name());
    }
}
```

App declares only a direct dependency on service. Thanks to `requires transitive` in service, app can read the `Customer` type from model. If service only declared `requires com.acme.model;`, app wanting to use the `Customer` type directly would also have to declare `requires com.acme.model;`.

Compile all three modules from the directory containing `src`:

```bash
javac --module-source-path src -d out \
  -m com.acme.model,com.acme.service,com.acme.app
```

Run the application:

```bash
java --module-path out \
  -m com.acme.app/com.acme.app.Main
```

Output:

```text
C01 - An
```

The example shows the app module calling the service API, service using its own internal package, and model providing publicly exported data types. These relationships are described by descriptors rather than relying solely on development team conventions.

## 8. What happens when a module violates boundaries?

If app tries to import:

```java
import com.acme.service.internal.CustomerRepository;
```

while `com.acme.service` does not export the `com.acme.service.internal` package, using this type from the app module will be rejected at compile time or when resolving module access permissions. Having `CustomerRepository` declared `public` cannot bypass the module boundary.

If the app module does not declare readability to the module containing a needed type, the compiler will also not treat that type as available API for app. Similarly, if a module declares a mandatory dependency but that module is absent from the module path, module resolution will fail.

A package should also not be shared simultaneously among multiple named modules in the same module graph. Let one module own the package and export the necessary API to other modules. This helps avoid split packages and clarifies responsibility for each namespace.

The module system supports architectural encapsulation and access control. It is not a security sandbox for running untrusted code; module boundaries should not be treated as a secure isolation mechanism replacing application and runtime security measures.

## 9. How to choose `requires`, `exports`, and `opens`

When designing a module, you can ask yourself in turn:

1. **Which modules does this module need to use?** Declare `requires` for direct dependencies.
2. **Do types from a dependency appear in the public API?** If API consumers need to read the dependency module through the current module, consider `requires transitive`.
3. **Which packages are API for other modules?** Export only the packages that need to be exposed using `exports`.
4. **Does a framework need deep reflection into any package?** Open only the necessary packages with `opens`, and restrict recipient modules if possible.
5. **Which packages are solely for implementation?** Keep them unexported so other modules cannot depend directly on internal details.

A good design typically has few exported packages, clear dependencies, and implementation packages kept within their owning module. When internal changes are needed, the module can change its implementation with minimal impact on API consumers.

## Summary

- **Encapsulation:** a module groups packages belonging to the same component and has its own descriptor.
- **Dependencies:** `requires` declares modules needed to be read; `requires transitive` propagates readability to users of the current module.
- **Package hiding:** only packages with `exports` become ordinary API for other modules; unexported packages remain usable inside the module.
- **Reflection:** `opens` permits deep access at runtime and can be restricted to specific modules.
- **Layered access control:** module exports, Java modifiers, and member access permissions work together to form the effective boundary.

When looking at `module-info.java`, read it as an architectural map of the module: what the module needs, which packages it exposes, and where it permits frameworks deep access. That is how JPMS helps Java systems have transparent dependencies, clean APIs, and tighter implementation hiding.