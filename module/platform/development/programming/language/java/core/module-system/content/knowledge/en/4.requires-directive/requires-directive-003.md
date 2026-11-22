# `requires transitive` and Transitive Dependencies

In the Java Platform Module System (JPMS), each module declares the modules it needs to read using the `requires` directive in `module-info.java`. By default, a module only receives direct readability to the modules it declares. The `requires transitive` directive extends that readability to downstream modules: any module that requires the current module can also read the module declared as a transitive dependency.

This mechanism is especially useful when a module's public API uses data types provided by another module. Consumers of the API can work with those types without having to re-declare the same dependency in every consuming module.

## 1. Distinguishing `requires` and `requires transitive`

Suppose there are three modules:

- `com.example.model` provides the `Customer` data type.
- `com.example.service.api` provides the service API and uses `Customer` in a public method signature.
- `com.example.app` uses the service API.

When the service module declares:

    requires com.example.model;

then `com.example.service.api` can read `com.example.model`. However, another module that only declares `requires com.example.service.api;` will not automatically have permission to read `com.example.model`.

If the service module declares:

    requires transitive com.example.model;

then any module that reads `com.example.service.api` also has its readability extended to `com.example.model`. Therefore, the application can use the public types of the model module through the service API without needing to declare a separate `requires com.example.model;` directive.

| Directive | Declaring module reading the dependency | Modules requiring the current module |
|---|---|---|
| `requires B;` | Reads B | Do not automatically read B through the current module |
| `requires transitive B;` | Reads B | Receive propagated readability to B |

The main relationship can be represented as follows:

    com.example.app
          |
          | requires
          v
    com.example.service.api
          |
          | requires transitive
          v
    com.example.model

The application reads the service module; because the service module exposes the model dependency as transitive, the application can also read the model module.

## 2. Three-Module Example

Directory structure:

    src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Customer.java
    ├── com.example.service.api/
    │   ├── module-info.java
    │   └── com/example/service/api/CustomerService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

### The model module

File `src/com.example.model/module-info.java`:

    module com.example.model {
        exports com.example.model;
    }

The model module exports the `com.example.model` package so modules reading it can access public types in the package.

File `src/com.example.model/com/example/model/Customer.java`:

    package com.example.model;

    public record Customer(long id, String name) {
    }

### The service API module

File `src/com.example.service.api/module-info.java`:

    module com.example.service.api {
        requires transitive com.example.model;
        exports com.example.service.api;
    }

This module reads model and propagates readability to model for modules that require it.

File `src/com.example.service.api/com/example/service/api/CustomerService.java`:

    package com.example.service.api;

    import com.example.model.Customer;
    import java.util.Optional;

    public interface CustomerService {
        Optional<Customer> findById(long id);
    }

The `Customer` type from the model module appears in the public method signature `findById`. This is an appropriate reason for the service API to declare `requires transitive`: modules consuming the API also need to read the `Customer` type to use that signature fully.

### The application module

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.service.api;
    }

The application only needs to require the service API module. There is no need to declare an additional `requires com.example.model;` to reference the `Customer` type exported by the model module.

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.model.Customer;
    import com.example.service.api.CustomerService;

    public class Main {
        public static void printFirstCustomer(CustomerService service) {
            service.findById(1L)
                    .ifPresent(customer -> System.out.println(customer.name()));
        }
    }

In this example, the application can import both `CustomerService` and `Customer`. Readability to the model module is propagated from the service API module via the `requires transitive` directive.

## 3. Compiling the Example

Arrange the three modules according to the directory structure above, then run the command from the directory containing `src`:

    javac --module-source-path src -d out -m com.example.model,com.example.service.api,com.example.app

The compile command locates the sources of the three modules by directory name, compiles them, and places the output in `out`.

You can inspect the service module descriptor:

    jar --describe-module --file out/com.example.service.api/module-info.class

In practice, `jar --describe-module` is typically used with a module JAR file. For an exploded module output structure, you can inspect it with:

    java --module-path out --describe-module com.example.service.api

The module description output will show `requires transitive com.example.model` along with the exported package.

## 4. What happens if changed to a regular `requires`?

If you change the service module to:

    module com.example.service.api {
        requires com.example.model;
        exports com.example.service.api;
    }

then the service API still reads `Customer` and still compiles the `Optional<Customer>` signature.

However, the application module declaring only:

    module com.example.app {
        requires com.example.service.api;
    }

will not read the model module. When `Main` imports `com.example.model.Customer`, the compiler reports that the package belonging to module `com.example.model` is not read by module `com.example.app`.

For the regular `requires` version to work, the application must declare directly:

    module com.example.app {
        requires com.example.service.api;
        requires com.example.model;
    }

The difference lies in the JPMS readability graph: `requires` creates a direct dependency for the declaring module; `requires transitive` additionally propagates readability of that dependency to modules that require the declaring module.

## 5. Readability and exports are two different things

This is the easiest point to confuse when learning `requires transitive`.

- **Readability** answers: does the current module have permission to read the types of the other module?
- **Exports** answers: does the module being read allow access to a specific package?

`requires transitive` propagates module readability. It does not automatically export packages, does not open packages for reflection, and does not bypass the target module's encapsulation boundaries.

In the example, `com.example.model` must still have:

    exports com.example.model;

If this `exports` line is removed, the application can read the model module but still cannot access the public `Customer` type in the unexported package. To use a package, the consuming module must have readability to the module containing the package and that package must be exported appropriately.

## 6. When should `requires transitive` be used?

Consider this directive when a module exposes an API where types from a dependent module appear in public positions, such as:

- Parameter types or return types of public methods.
- Generic types in API signatures, for example `Optional<Customer>` or `List<Customer>`.
- Supertypes or interfaces that API consumers need to see in order to use or implement the contract.

If a module only uses a library in its internal implementation and does not expose types from that library through its public API, regular `requires` is usually the better choice.

You should not convert every dependency into `requires transitive` out of habit. Each transitive directive increases the number of modules that consumers can read and widens the module's public dependency surface. Only propagate dependencies that are genuinely part of the API contract.

## 7. What `requires transitive` does not mean

1. **It is not re-exporting packages.** Packages are still governed by the owning module via `exports`.
2. **It does not automatically add libraries to every build configuration.** JPMS controls module readability on the module path; Gradle or Maven still manages finding and supplying artifacts.
3. **It does not mean the consuming module is forced to call APIs of the dependent module.** It is simply granted readability according to the module graph.
4. **It does not completely replace direct dependency declarations.** If the application depends directly on model as part of its own design, declaring `requires com.example.model;` can still clarify the application's contract.
5. **It does not turn an unexported package into a public package.** Readability and exports must both be satisfied.

## 8. Comparison with Gradle/Maven dependency transitivity

The names look similar, but the two concepts live at two different layers:

- Gradle/Maven dependency transitivity describes how the build tool resolves and brings dependent artifacts into a configuration or classpath/module path.
- `requires transitive` is a directive in `module-info.java` that defines readability relationships between named modules under JPMS.

A library can be resolved successfully by Gradle/Maven, yet module source code still cannot access a package if the module descriptor does not declare the appropriate relationship. Conversely, a directive in `module-info.java` does not automatically download missing artifacts to your machine. Build configuration and module descriptors must be consistent.

## Key Takeaways

When you see:

    module A {
        requires transitive B;
    }

understand that A reads B, and any module that requires A is also propagated readability to B. Use `requires transitive` when B is part of the API that A exposes. Then also verify that B has exported the necessary packages using `exports`.

Quick check question: if `com.example.app` only declares `requires com.example.service.api;`, why can it still import `Customer` from `com.example.model`? Because `com.example.service.api` declares `requires transitive com.example.model;`, so readability to model is propagated to the application.