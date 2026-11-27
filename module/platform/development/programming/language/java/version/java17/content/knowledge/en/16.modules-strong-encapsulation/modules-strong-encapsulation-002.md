# `module-info.java`, `requires`, and Module Readability in Java 17

The Java Platform Module System (JPMS) organizes applications into named **modules**, declares dependencies, and controls which packages can be used by other modules. Within each named module, the `module-info.java` file serves as the module descriptor. The `requires` directive declares that the current module depends on another module and establishes a **readability** relationship — the ability of one module to read types provided by another.

Three concepts should be kept distinct:

- **Module descriptor:** declares the module name, dependencies, and exposed packages.
- **`requires`:** specifies which modules must be read at compile time and runtime.
- **Readability:** determines which modules can see types belonging to another module; package access also depends on `exports` and Java access rules.

Example of an application module:

```java
module com.example.app {
    requires java.sql;
    requires com.example.service;
}
```

This declaration states that `com.example.app` needs to read `java.sql` and `com.example.service`. It does not mean every package in those two modules is automatically exposed to the application. The required module must still export the appropriate packages.

> **Version:** JPMS was introduced in Java 9 and remains the official module foundation in Java 17. The examples use stable syntax without requiring preview features.

## 1. What Is a Module?

A **module** is a named unit for organizing code and dependencies. A module can contain:

- Packages and classes/interfaces/records.
- A module descriptor `module-info.java`.
- Dependencies on other modules.
- Rules for exporting packages to other modules.
- Rules for opening packages for reflection when needed.

Compared to a package, a module has a larger scope:

| Package | Module |
|---|---|
| Groups related types by namespace | Groups packages into a deployment and dependency unit |
| Avoids type name collisions | Controls which module reads which module |
| Has package and member access rules | Adds module-level export/open boundaries |
| Does not declare dependencies on other packages itself | Declares dependencies via `requires` |

Example:

```text
com.example.application
├── module-info.java
└── com/example/application/
    ├── Main.java
    └── config/
        └── Settings.java
```

The module directory contains a module descriptor at the root of the module source. Packages reside underneath following standard package layout.

### 1.1. Named modules and the classpath

Java 17 still supports running applications on the classpath. When classes are placed on the classpath without belonging to a named module, they typically reside in the **unnamed module** of the corresponding class loader.

Named modules are described by `module-info.java` and located via the **module path**. These are two different deployment models:

| Model | Loading mechanism | Has a project-declared module descriptor? |
|---|---|---|
| Classpath | `--class-path` or `-cp` | Optional; classpath code belongs to the unnamed module |
| Named module | `--module-path` or `-p` | Has `module-info.java` in the module |
| Automatic module | JAR without a descriptor placed on the module path | No explicit descriptor; module name is derived or declared in the manifest |

For new projects requiring clear module boundaries, declare explicit named modules. Automatic modules remain a useful compatibility mechanism when integrating JAR libraries without module descriptors; do not confuse them with a module whose dependencies and exports are fully controlled by the project.

## 2. What Is `module-info.java`?

`module-info.java` is a special source file containing the module declaration. It resides at the **root of the module source**, not inside a package like regular classes.

Example structure:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
```

Contents of `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

The module name here is `com.example.app`. It is a module identifier and does not strictly have to match the directory name, package name, or JAR file name, though the reverse-domain convention is commonly used to reduce naming collisions.

### 2.1. Basic syntax

```java
module module.name {
    requires another.module;
    exports public.package;
    opens reflective.package;
}
```

A module descriptor can contain multiple directives. This lesson focuses on `requires` and readability; `exports` and `opens` are mentioned to distinguish module readability from package accessibility.

### 2.2. Module name

Module names typically follow reverse-domain form:

- `com.example.app`
- `org.acme.orders`
- `vn.company.billing`

Each segment of the name follows Java identifier rules. Avoid generic names like `utils` or `common` if the module may be shared across a larger system.

The name written in `requires` is a **module name**, not a package name:

```java
module com.example.app {
    requires java.sql; // Module name
}
```

`java.sql` is the module name of the SQL API in the JDK. It contains the `java.sql` package, but module name and package name are two distinct concepts even when they look identical.

### 2.3. One named module has one descriptor

A source module has one module declaration. `module-info.java` is not a regular class and is not placed inside a package. Do not declare multiple modules in the same descriptor.

Source files belonging to a named module must reside in named packages; the unnamed package cannot be used inside a named module.

## 3. The `requires` Directive

`requires` declares that the current module needs to **read** another module:

```java
module com.example.app {
    requires java.sql;
    requires com.example.model;
}
```

Here, `com.example.app` can read public types belonging to packages exported by `java.sql` and `com.example.model`.

Standard syntax:

```java
requires module.name;
```

Each `requires` directive ends with a semicolon.

### 3.1. `requires` is a module-level dependency

Suppose module `com.example.model` contains:

```java
package com.example.model;

public record Customer(String id, String name) {}
```

Model module descriptor:

```java
module com.example.model {
    exports com.example.model;
}
```

An application module wanting to use `Customer` needs to declare:

```java
module com.example.app {
    requires com.example.model;
}
```

It can then import the exported type:

```java
package com.example.app;

import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "An");
        System.out.println(customer.name());
    }
}
```

Without `requires com.example.model;`, the app module has no readability edge to model and cannot use types from that module under normal module rules.

If the model module does not export `com.example.model`, adding `requires` alone is still not enough for app to access `Customer`. `exports` is explained in section 9.

### 3.2. `requires` applies at both compile time and runtime

Regular dependencies are checked at compile time and used by the module resolver when launching the application. The required module must be observable and resolvable on the module path or in the runtime image.

If the module is not found, you may encounter an error such as:

```text
error: module not found: com.example.model
```

At runtime, if a required module is missing from the module graph, startup may fail with a module resolution error. Therefore, configure the module path properly for both compile and run steps.

## 4. Module Readability

A module **reads** another module when it is permitted to reference types provided by that module, subject to package exports and accessibility rules.

Example:

```java
module com.example.app {
    requires com.example.model;
}
```

Readability relationship:

```text
com.example.app  ──requires──>  com.example.model
      │                               │
      └──────── reads ────────────────┘
```

You can think of the `requires` arrow as a dependency declared from the consuming module to the required module.

### 4.1. Readability is not inheritance

`requires` does not cause classes in one module to inherit from classes in another module. Nor does it automatically import packages.

After establishing readability, Java code still needs `import` if using unqualified type names:

```java
import com.example.model.Customer;
```

Or it can write the fully qualified name:

```java
com.example.model.Customer customer =
        new com.example.model.Customer("C01", "An");
```

`import` is source-file syntax; `requires` is a dependency in the module descriptor. They solve two different levels of problems.

### 4.2. Readability is directional

If module A requires module B, A reads B. That does not automatically create the reverse relationship:

```text
A ──requires──> B

A reads B
B does not automatically read A
```

If B also needs to use public types exported by A, B must declare the appropriate dependency. Never assume dependencies are bidirectional.

### 4.3. Readability can be propagated via requires transitive

`requires transitive` creates a readability relationship that is passed on to dependent modules. This is important when a module exposes types from a dependency in its own API.

The next section explains this in detail.

## 5. `requires transitive` — Propagating Readability to Dependent Modules

Syntax:

```java
module com.example.service {
    requires transitive com.example.model;
}
```

This directive has two meanings:

1. Module `com.example.service` reads `com.example.model`.
2. Other modules requiring `com.example.service` also read `com.example.model` through the transitive relationship.

Visualized as:

```text
com.example.app
      |
      | requires
      v
com.example.service
      |
      | requires transitive
      v
com.example.model

Result: app reads service and model.
```

### 5.1. Three-module example

Suppose there are three modules:

- `com.example.model`: contains data type `Customer`.
- `com.example.service`: provides a service working with `Customer`.
- `com.example.app`: application using the service.

**Model module**

```java
module com.example.model {
    exports com.example.model;
}
```

File `Customer.java`:

```java
package com.example.model;

public record Customer(String id, String name) {}
```

**Service module**

```java
module com.example.service {
    requires transitive com.example.model;
    exports com.example.service;
}
```

File `CustomerService.java`:

```java
package com.example.service;

import com.example.model.Customer;

public class CustomerService {
    public Customer findCustomer(String id) {
        return new Customer(id, "An");
    }
}
```

The public API of service uses `Customer` in its return type. Therefore, service declares `requires transitive com.example.model` so client modules reading service can also read model.

**App module**

```java
module com.example.app {
    requires com.example.service;
}
```

File `Main.java`:

```java
package com.example.app;

import com.example.model.Customer;
import com.example.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findCustomer("C01");

        System.out.println(customer.name());
    }
}
```

App only declares `requires com.example.service`, yet it can still use `Customer` because service declared its dependency on model as transitive.

### 5.2. What if service uses normal requires?

If the service module declares:

```java
module com.example.service {
    requires com.example.model;
    exports com.example.service;
}
```

then service still reads model and can use `Customer` in its implementation/API. However, the app module that only `requires com.example.service` **does not automatically read model**.

If app needs to reference `Customer`, app must additionally declare:

```java
module com.example.app {
    requires com.example.service;
    requires com.example.model;
}
```

Thus, the difference is not whether service uses model; the difference is **whether the model dependency is propagated to client modules**.

### 5.3. When should you use transitive?

Use `requires transitive` when the dependency is part of the API that the module wants clients to be able to use directly.

Examples:

- An API module returns types from a model module.
- A facade module exposes collection types or abstractions from a dependency.
- A library module is designed to re-export readability of a dependency that clients need to compile.

Do not use transitive merely because a module's implementation calls a library. If a dependency is only used internally, normal `requires` keeps the module graph cleaner and avoids forcing clients to know about that dependency.

**Design rule:** dependencies appearing in public types of the API may need to be transitive; dependencies confined to implementation usually only need regular `requires`. Evaluate the actual API contract rather than applying it mechanically.

## 6. `requires static` — Mandatory at Compile Time, Optional at Runtime

Syntax:

```java
module com.example.app {
    requires static com.example.annotations;
}
```

`requires static` expresses a dependency needed when compiling the module, but which does not need to be resolved at runtime.

It is useful for dependencies serving compilation only or present only in certain execution environments, such as annotations with appropriate retention that are not used as mandatory runtime dependencies.

### 6.1. Example with compile-time annotations

Suppose module `com.example.annotations` contains an annotation:

```java
package com.example.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface GeneratedMarker {}
```

Descriptor:

```java
module com.example.annotations {
    exports com.example.annotations;
}
```

Consuming module:

```java
module com.example.app {
    requires static com.example.annotations;
}
```

Source:

```java
package com.example.app;

import com.example.annotations.GeneratedMarker;

@GeneratedMarker
public class GeneratedType {}
```

The app module needs the annotations module on the module path at compile time so the compiler can locate the annotation type. At runtime, an annotation with `CLASS` retention is not required for the application to read via reflection, so the dependency does not need to be resolved.

### 6.2. `requires static` does not mean "use if present, otherwise everything keeps working"

If code actually needs to load a class from the optional module at runtime, lacking that module can cause errors when that code path executes. `requires static` does not create a fallback automatically and does not replace plugin mechanisms or dependency presence checks.

Use it for dependencies that are genuinely optional at runtime. If the application always needs that module to function, use regular `requires`.

### 6.3. Comparing requires and requires static

| Directive | At compile time | At runtime | Purpose |
|---|---|---|---|
| `requires M;` | Module M must be resolvable | M is a mandatory dependency | Required dependency of the module |
| `requires static M;` | M must be present to compile | M is not required to be in the runtime graph | Compile-time or runtime-optional dependency |

A module can combine `static` with `transitive` if a dependency is both optional at runtime and needs to propagate readability to dependent modules in appropriate contexts:

```java
requires static transitive com.example.annotations;
```

Use this combined form only when the API contract truly requires it.

## 7. `requires transitive` and `requires static transitive`

The two modifiers address two different aspects:

- `transitive`: propagates readability of the dependency to modules requiring the current module.
- `static`: dependency is needed at compile time but may be absent at runtime.

Both can be used together:

```java
module com.example.api {
    requires static transitive com.example.optional.annotations;
}
```

Reading each part:

1. `com.example.api` requires the annotations module at compile time.
2. Modules depending on `com.example.api` can receive propagated readability to the annotations module within the corresponding module graph.
3. The dependency remains marked optional at runtime.

This is a specialized declaration, not the default form. Consider whether client modules genuinely need to see that dependency.

## 8. `java.base` Is Read Implicitly

Every named module, except `java.base` itself, has readability to `java.base` by the rules of the module system. Therefore, you do not need to write:

```java
module com.example.app {
    requires java.base; // No explicit declaration needed
}
```

Foundational types like `String`, `Object`, `List`, `System`, `RuntimeException`, and many core APIs belong to `java.base`.

For example, a module descriptor can simply be:

```java
module com.example.app {
}
```

The code can still use:

```java
package com.example.app;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names);
    }
}
```

`requires java.base` is not needed. Writing this dependency explicitly is usually unnecessary and may trigger a redundant warning from the compiler.

Other JDK modules such as `java.sql`, `java.logging`, and `java.net.http` are not automatically read simply because they belong to the JDK; if using APIs from them in a named module, declare the appropriate dependency.

Example:

```java
module com.example.database {
    requires java.sql;
}
```

## 9. Readability Differs from exports and opens

This is a very important distinction when learning JPMS.

**`requires` establishes module readability. `exports` controls which packages are accessible to other modules. `opens` allows deep reflection into packages within the declared scope.**

### 9.1. Having requires without exports

Library module:

```java
module com.example.internal {
    // Does not export package com.example.internal.api
}
```

It has a public class:

```java
package com.example.internal.api;

public class SecretService {
    public void execute() {}
}
```

Client module:

```java
module com.example.client {
    requires com.example.internal;
}
```

Even though client reads module `com.example.internal`, package `com.example.internal.api` is not exported. Thus client cannot access `SecretService` as a public API of the module.

**Readability is a necessary condition, not a sufficient condition for accessing every type.**

### 9.2. Exporting a package

Library module:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Client module:

```java
module com.example.client {
    requires com.example.library;
}
```

Client can then use public types in `com.example.library.api`, provided other Java access rules are also satisfied.

`exports` does not make every package inside the library public. Only exported packages are opened for normal access from other modules.

### 9.3. Qualified exports

A package can be exported to specific modules:

```java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.internal.spi to com.example.plugin;
}
```

Package `com.example.library.internal.spi` is only exported to module `com.example.plugin` as a qualified export. Other modules do not automatically gain access to this package.

### 9.4. Opens serves reflection

`opens` is not the same as `exports`. It allows frameworks or reflection libraries to perform deep access into package members at runtime according to module system rules:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
```

This is often required by object-mapping, dependency injection, or serialization frameworks that use deep reflection. If you only want to expose a normal Java API, use `exports`.

| Directive | Purpose | Primary phase/function |
|---|---|---|
| `requires` | Current module reads another module | Readability |
| `requires transitive` | Propagates dependency readability to clients | Indirect readability |
| `exports` | Exposes package to other modules | Public type access |
| `opens` | Allows deep reflection into package | Runtime reflection |

Do not add `opens` just to fix a package import error; import errors usually require checking `requires` and `exports`.

## 10. The Module Graph and How Dependencies Are Read

When launching a modular application, the JVM builds a module graph from the root modules and their dependencies. Each `requires` directive creates an edge in the graph; the `transitive` modifier affects how readability propagates.

Example:

```java
module com.example.app {
    requires com.example.service;
}

module com.example.service {
    requires transitive com.example.model;
}

module com.example.model {
    exports com.example.model;
}
```

Diagram:

```text
             requires
com.example.app ───────────> com.example.service
                                  |
                                  | requires transitive
                                  v
                            com.example.model

Readability:
- app reads service (direct)
- service reads model (direct)
- app reads model (transitive)
```

If service changes to a normal `requires com.example.model`, app no longer reads model automatically. App must add `requires com.example.model` if app's source references types in the model module.

### 10.1. Readability does not mean "read all dependencies of dependencies"

Module A requiring B does not mean A automatically reads every module B requires. Only dependencies propagated via `requires transitive` pass readability along under this rule.

Example:

```text
app --requires--> service --requires--> model

app reads service
service reads model
app does not automatically read model
```

If the edge from service to model is `requires transitive`, app will read model:

```text
app --requires--> service --requires transitive--> model

app reads service
app also reads model
```

This is why transitive should be designed intentionally rather than enabled for every dependency.

### 10.2. No cyclic dependencies

The module graph must be resolvable without creating `requires` cycles. Example:

```java
// module A
module com.example.a {
    requires com.example.b;
}

// module B
module com.example.b {
    requires com.example.a;
}
```

Two modules depending cyclically on each other is an invalid structure for the module graph. When encountering this error, review responsibility boundaries: extract shared APIs into a third module, or invert the dependency direction using an interface/service abstraction.

Example resolution:

```text
          com.example.a
                |
                v
          com.example.api
                ^
                |
          com.example.b
```

Both A and B depend on the shared API; the API does not depend back on A or B.

## 11. Module Path and Module Resolution

`module-info.java` only describes dependencies; the compiler and JVM still need to locate the actual modules. The module path is where modules reside as exploded directories, modular JARs, or other valid module formats.

### 11.1. Compiling with module source path

A multi-module project layout might look like:

```text
project/
└── src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Customer.java
    ├── com.example.service/
    │   ├── module-info.java
    │   └── com/example/service/CustomerService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

Compile all modules:

```bash
javac --module-source-path src -d out \
  -m com.example.model,com.example.service,com.example.app
```

`--module-source-path` points to the source tree containing the modules; `-d out` specifies the output directory for compiled classes/modules; `-m` selects the modules to compile.

### 11.2. Running a module

```bash
java --module-path out \
  -m com.example.app/com.example.app.Main
```

The syntax `-m module/class` selects the main module and main class. The JVM resolves the modules required by app according to the module graph.

You can abbreviate `--module-path` to `-p` and `--module` to `-m`.

### 11.3. Compiling a module using a JAR dependency

If the model module has already been packaged as a JAR:

```bash
javac --module-path lib \
  -d out/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

The `lib` directory must contain a JAR/module whose name matches the `requires` directive. The module name is determined from the descriptor or automatic module rules, not simply the JAR file name.

### 11.4. Module path differs from classpath

| Option | Role |
|---|---|
| `--class-path` / `-cp` | Locates classes and resources on the classpath |
| `--module-path` / `-p` | Locates modules for the module resolver to build the module graph |
| `--module` / `-m` | Selects the module and main class to run |
| `--module-source-path` | Locates sources of multiple modules when compiling |

Placing a JAR on the classpath is not equivalent to placing it on the module path. To control dependencies with `requires`, you need to understand which model is resolving that module.

## 12. Inspecting Module Descriptors and the Module Graph

JDK 17 includes useful command-line tools.

### 12.1. javac reports module not found

If you encounter:

```text
error: module not found: com.example.model
```

Check:

- Is the module on the module source path or module path?
- Is the module name in `module-info.java` correct?
- Is the module selected/included in the compilation?
- Are you using `--module-path` or only `--class-path`?
- Does the JAR have a module descriptor or automatic module name matching what the dependency expects?

### 12.2. Listing modules in the JDK

The command:

```bash
java --list-modules
```

lists observable modules in the runtime image/module path under the run configuration.

To describe a module:

```bash
java --describe-module java.sql
```

You can use a similar command for application modules when they are on the module path:

```bash
java --module-path out --describe-module com.example.app
```

The output shows which directives and related packages the module has, which is useful when checking module names or exports/requires.

### 12.3. Reading descriptors inside a JAR

The `jar --describe-module` command inspects a JAR's descriptor:

```bash
jar --describe-module --file lib/example.jar
```

If the JAR is an automatic module, the output can indicate the automatic module name. This is a helpful check when integrating external libraries.

## 13. Common Errors with requires and Readability

| Symptom | Possible cause | Resolution |
|---|---|---|
| `module not found` | Module missing from module path or misspelled name | Check the module path and the name in the descriptor |
| `package ... is not visible` | Module not read or package not exported | Check `requires` and `exports` |
| Client cannot use types in a service's dependency | Service uses normal `requires`, not propagating readability | Client adds direct `requires` or service uses `transitive` if appropriate for the API contract |
| Assuming `requires` makes packages public | Confusing readability with exports | Providing module must export the needed package |
| Missing module at runtime | Required dependency was not resolved | Place the module on the module path/runtime image |
| Cycle in module graph | Two or more modules cyclically require each other | Extract shared API or adjust dependency direction |
| Works on classpath, fails on module path | Different loading and encapsulation modes | Check descriptors, exports, requires, and module path |

### 13.1. Missing requires error

Module descriptor:

```java
module com.example.app {
    // Missing requires com.example.model;
}
```

Source:

```java
import com.example.model.Customer;
```

If `Customer` belongs to named module `com.example.model`, the app module must declare a dependency on that module or receive readability through a valid transitive path.

### 13.2. Unexported package error

Library module descriptor:

```java
module com.example.library {
    // Does not export com.example.library.api
}
```

Client already has:

```java
module com.example.client {
    requires com.example.library;
}
```

Client still cannot import types in the unexported package. Fix the providing module with:

```java
module com.example.library {
    exports com.example.library.api;
}
```

If the package is meant for internal implementation only, do not export it just to silence the compiler; define the module's true public API.

### 13.3. Using requires transitive too broadly

If a service module only uses a model module inside its implementation, declaring it transitive forces every client of service to also see the model dependency. This increases coupling and enlarges the application's module graph.

Only propagate readability when the dependency is part of the API contract or has a clear design reason.

## 14. Readability and Strong Encapsulation

JPMS is designed to strengthen encapsulation. Before the module system, the classpath often allowed many packages to be visible across a wide space; the module system introduces clear boundaries between modules.

Strong encapsulation relies on these mechanisms:

1. Modules declare which packages are exported.
2. Client modules declare dependencies with `requires`.
3. Unexported packages do not become regular APIs for other modules.
4. Deep reflection is governed by `opens` and corresponding access rules.

Example:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Packages `com.example.library.internal` and `com.example.library.impl` can still exist in the module without being exported. Clients should not depend on their implementation details.

### 14.1. A public class is not necessarily a public cross-module API

```java
package com.example.library.internal;

public class InternalCache {}
```

The `public` modifier only addresses Java language access level. If the package is not exported, other modules cannot use that class as a normal API.

### 14.2. Requires does not break encapsulation

```java
module com.example.client {
    requires com.example.library;
}
```

This declaration does not mean client is allowed to access every package in library. It only establishes readability. Which packages can be used still depends on exports and type/member accessibility.

### 14.3. Do not rely on JDK internal APIs

In new applications, only use public APIs documented by Java SE/JDK. The module system enforces stronger encapsulation over JDK internal implementations; relying on internal packages like `sun.*` or `com.sun.*` makes applications brittle during upgrades.

Do not design dependencies around widening access to JDK implementation details when a supported public API exists.

## 15. Designing requires in Multi-Module Applications

A maintainable module graph usually has dependencies flowing in one clear direction.

Layered example:

```text
             com.example.app
                    |
                    v
            com.example.service
                    |
                    v
             com.example.model

             com.example.api
             (if contract needs to be separated)
```

Some principles:

- Higher-level application modules can depend on services.
- Services can depend on models or APIs.
- Model modules should rarely depend on application layers.
- Avoid cyclic dependencies.
- Use `requires transitive` when a dependency genuinely appears in the public API and clients need to read it.
- Keep implementation dependencies as normal `requires`.
- Do not add every JDK module to the descriptor "just in case"; declare only the modules actually needed by code or the module descriptor.

### 15.1. A module can require multiple modules

```java
module com.example.reporting {
    requires java.sql;
    requires java.logging;
    requires com.example.model;
    requires com.example.service;
}
```

Each directive is a separate dependency. The module names must exist in the module graph.

### 15.2. Do not require a package

Incorrect:

```java
module com.example.app {
    // Wrong: this is a package name, not a module name.
    // requires com.example.model.api;
}
```

Correct if `com.example.model` is the module name:

```java
module com.example.app {
    requires com.example.model;
}
```

Package `com.example.model.api` can be exported by module `com.example.model`. `requires` always targets a module.

### 15.3. Do not require a JAR file name

If the file is `customer-model-1.0.jar`, do not blindly write:

```java
requires customer-model-1.0;
```

unless that is genuinely the module name determined by the descriptor or automatic module rules. Check using `jar --describe-module` or `java --describe-module`.

## 16. Complete Three-Module Example Running on JDK 17

Structure:

```text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/Customer.java
├── com.example.service/
│   ├── module-info.java
│   └── com/example/service/CustomerService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

**1. Model module**

```java
// src/com.example.model/module-info.java
module com.example.model {
    exports com.example.model;
}
```

```java
// src/com.example.model/com/example/model/Customer.java
package com.example.model;

public record Customer(String id, String name) {}
```

**2. Service module**

```java
// src/com.example.service/module-info.java
module com.example.service {
    requires transitive com.example.model;
    exports com.example.service;
}
```

```java
// src/com.example.service/com/example/service/CustomerService.java
package com.example.service;

import com.example.model.Customer;

public class CustomerService {
    public Customer find(String id) {
        return new Customer(id, "An");
    }
}
```

**3. App module**

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.service;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.model.Customer;
import com.example.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.find("C01");

        System.out.println(customer.id() + ": " + customer.name());
    }
}
```

Compile from the project directory:

```bash
javac --module-source-path src -d out \
  -m com.example.model,com.example.service,com.example.app
```

Run:

```bash
java --module-path out \
  -m com.example.app/com.example.app.Main
```

Output:

```text
C01: An
```

Why can app use `Customer` even though app only requires service?

- Service directly requires model.
- Service declares that dependency as transitive.
- App requires service, so readability to model is propagated to app.
- Model exports package `com.example.model`, so app can access the `Customer` type.

If `requires transitive com.example.model` is changed to `requires com.example.model`, app would need to add `requires com.example.model` to use `Customer` directly.

## 17. Practice Exercises

### Exercise 1 — Reading a module descriptor

Given:

```java
module com.example.order {
    requires java.sql;
    requires com.example.customer;
}
```

**Question:** Which directly declared modules does `com.example.order` read?

**Answer:** `java.sql` and `com.example.customer`. This module also has implicit readability to `java.base`.

### Exercise 2 — Does requires open packages?

Module A:

```java
module com.example.a {
    exports com.example.a.api;
}
```

Module B:

```java
module com.example.b {
    requires com.example.a;
}
```

**Question:** Can B access every package in A?

**Answer:** No. B reads module A, but only exported packages can be accessed under module rules. Unexported packages remain closed to other modules.

### Exercise 3 — Requires transitive

A requires B; B requires transitive C. Does A read C?

**Answer:** Yes. B's transitive dependency propagates readability to A.

### Exercise 4 — Regular requires

A requires B; B requires C (not transitive). Does A automatically read C?

**Answer:** No. A reads B; B reads C. Readability does not propagate automatically through regular dependencies.

### Exercise 5 — Choosing requires vs requires transitive

A service module uses model in its implementation without exposing model types in its public API. Which should be chosen?

**Answer:** Regular `requires`. There is no need to force clients to read model if clients do not need to reference it.

### Exercise 6 — Compile-time optional dependency

A module uses an annotation needed only by the compiler; the annotation has `CLASS` retention and is not read by the application via reflection at runtime. Which directive can be considered?

**Answer:** `requires static`. The annotations module must be present at compile time; the dependency might not be needed in the runtime graph. If actual code needs that class at runtime, a clear runtime dependency must be designed.

### Exercise 7 — Why not requires java.base?

**Answer:** Every named module other than `java.base` reads `java.base` implicitly. No explicit directive is needed.

### Exercise 8 — Distinguishing package and module names

Module `com.example.library` exports package `com.example.library.api`. Which `requires` should the client module write?

**Answer:** `requires com.example.library;`. Do not write the package name in the directive.

## 18. Summary

- `module-info.java` is the module descriptor at the root of the module source.
- `requires M;` declares a direct dependency and causes the current module to read M.
- Readability is directional; A requiring B does not make B automatically read A.
- `requires transitive M;` propagates readability to modules that require the current module.
- `requires static M;` requires the dependency at compile time while allowing it to be absent at runtime.
- `java.base` is implicitly read by all other named modules.
- `requires` points to a **module name**, not a package name or JAR file name.
- Readability does not equal package access: the providing module must `exports` the needed package.
- `opens` serves deep reflection, distinct from `exports`.
- The module graph must not contain `requires` cycles.
- Use the module path to compile/run named modules; classpath and module path follow different loading rules.
- Use `requires transitive` intentionally when a dependency is part of the API contract; internal dependencies usually only need `requires`.

## Official References for Java 17

- [Java Language Specification 17 — `7.7`: Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [Java Language Specification 17 — `7.7.1`: Dependencies](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.1).
- [Java Language Specification 17 — `7.7.2`: Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2).
- [Java SE 17 API — `java.lang.module.ModuleDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html).
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
- [Oracle Java 17 — The Java Module System](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).
