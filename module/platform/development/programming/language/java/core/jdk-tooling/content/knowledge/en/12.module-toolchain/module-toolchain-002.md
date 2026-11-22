# requires in the Java Module System

In the Java Platform Module System (JPMS), the **requires** keyword declares that a module depends on and needs to read another module. This directive is written in the module descriptor file **module-info.java**. It helps the compiler and JVM build the module graph, determine which modules must be present at compile time or application startup, and control a module's visibility into packages exported by other modules.

Simple example:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

The module `com.acme.app` declares a dependency on the `java.sql` module. As a result, source code in `com.acme.app` can use public APIs in packages exported by `java.sql`, such as `java.sql.Connection`.

Note the distinction between **requires** and **exports**: `requires` states which modules the current module reads; `exports` is declared by the providing module to decide which packages are accessible to other modules. Simply declaring `requires` does not make all internal packages of a dependency public.

## 1. Location and Syntax

The `requires` directive resides inside the module declaration in `module-info.java`:

~~~java
module module.name {
    requires another.module;
}
~~~

General syntax:

~~~java
requires [static] [transitive] module.name;
~~~

The two modifiers can appear independently or together:

- No modifier: a mandatory dependency at compile time and when resolving the module graph at runtime.
- **transitive**: modules that depend on this module also gain readability of the dependency declared as `transitive`.
- **static**: a mandatory dependency at compile time, but optional at runtime.
- **static transitive**: readability of the dependency is propagated to dependent modules, while remaining an optional dependency at runtime.

The module name is the exact, case-sensitive module name. This name comes from the module descriptor or the automatic module name when a library does not yet have a `module-info.class`.

Example:

~~~java
module com.acme.data {
    requires java.sql;
    requires transitive com.acme.model;
    requires static com.acme.codegen;
}
~~~

A module can have multiple `requires` directives. Version ranges or library versions are not declared in `requires`; artifact version selection is typically managed by Maven, Gradle, packaging systems, or the deployment environment.

## 2. Modules and Module Descriptors

A named module typically has the following structure:

~~~text
project/
  src/
    com.acme.app/
      module-info.java
      com/
        acme/
          app/
            Main.java
~~~

The `module-info.java` file describes the module name and directives such as:

- **requires**: which modules the current module depends on and reads.
- **exports**: which packages are accessible to other modules.
- **opens**: which packages are opened for reflection.
- **uses**: a service interface that the module uses.
- **provides ... with ...**: an implementation provided for a service.

Example:

~~~java
module com.acme.app {
    requires java.sql;
    exports com.acme.app.api;
    opens com.acme.app.model to some.json.framework;
}
~~~

Here, `com.acme.app` reads the `java.sql` module, exports its own API package, and opens its `model` package to a specific framework module. These three directives solve three different concerns.

### java.base Is Implicitly Required

Every named module, except `java.base` itself, implicitly reads `java.base`. Therefore, a typical module does not need to write:

~~~java
module com.acme.app {
    // No need to declare requires java.base.
}
~~~

When inspecting the compiled descriptor with `javap -v`, `requires java.base` may appear with the **mandated** flag. This is a dependency implicitly added by the language/module system.

## 3. requires Creates a Module Readability Relationship

When module A declares:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

the module `com.acme.app` establishes a readability relationship with `com.acme.library`. If `com.acme.library` exports the package `com.acme.library.api`, code in `com.acme.app` can import and use public types in that package, provided other Java access conditions are also satisfied.

Example API-providing module:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

And the application module:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Java code in `app` can write:

~~~java
import com.acme.library.api.Greeting;
~~~

If the library module does not export the package containing `Greeting`, `app` can read the module but still cannot access types in that encapsulated package.

**Readability** and **accessibility** are two concepts that must be considered together:

1. `requires` makes the current module read the required module.
2. `exports` on the required module determines which packages are accessible from other modules.
3. Java access modifiers such as `public`, `protected`, package-private, and `private` continue to apply within packages and classes.
4. Reflection rules are also governed by `opens` and module access.

## 4. Direct requires and Transitive Dependencies

Suppose there are three modules:

- `app` uses `library`.
- `library` uses `model`.
- `model` exports an API package.

If `library` declares a plain `requires model`, `app` reads `library` but does not automatically read `model` merely because `library` depends on `model`.

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
module com.acme.library {
    requires com.acme.model;
    exports com.acme.library.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

In this configuration, `com.acme.app` cannot directly use `com.acme.model.api` solely by requiring `com.acme.library`.

If `library`'s public API uses types from `model` and you want consumers of `library` to be able to read those types through the dependency, `library` can declare:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
    exports com.acme.library.api;
}
~~~

When `app` requires `com.acme.library`, the transitive readability relationship allows `app` to read `com.acme.model`.

### requires transitive Is Not exports

The `transitive` modifier propagates readability of a module dependency to dependent modules. It does not export the dependency's packages by itself, nor does it make `library`'s internal packages public.

The `com.acme.model` module must still export the API packages that consumers need to access. If `model` does not export `com.acme.model.internal`, `app` cannot access that package just because `library` declares `requires transitive com.acme.model`.

### When to Use transitive?

Use `requires transitive` when a dependency appears in the module's public API and consumers of that module need to read the dependency in order to compile against or use the API.

For example, a public method returns `com.acme.model.api.Customer`. If the `library` module exports the package containing that method, a client module typically needs to read `model` to reference `Customer`. `requires transitive` expresses this module contract.

Do not declare `transitive` for every dependency. Doing so widens the consumer's module graph and can inadvertently turn implementation details into part of the dependency contract.

## 5. requires static: Compile-Time Mandatory, Runtime-Optional Dependencies

**requires static** declares a dependency that is required at compile time but does not have to be present at runtime.

~~~java
module com.acme.app {
    requires static com.acme.optional;
}
~~~

The compiler still needs to find `com.acme.optional` on the module path at compile time. At launch time, this module may be absent without causing module graph resolution to fail solely because of the `static` directive.

Use cases may include:

- APIs referenced only by compile-time annotations or metadata.
- Optional integrations with libraries that may not be installed in certain environments.
- Build or analysis tooling that does not need to be loaded at runtime.
- Extension features isolated so the core can run when the extension is absent.

### Precautions When the Dependency Is Absent

`requires static` does not make every call to the dependency safe. If runtime code actually loads a class, invokes a method, or instantiates an object from the optional module when that module is missing, the program can still fail with errors such as `NoClassDefFoundError` or a corresponding linkage error.

Therefore:

- Separate code that depends on optional modules from the mandatory startup path.
- Check feature availability by design.
- Avoid exposing types from optional dependencies in places that every mandatory caller must load.
- Test both when the dependency is present and when it is absent.

## 6. Combining static and transitive

Both modifiers can be used together:

~~~java
module com.acme.library {
    requires static transitive com.acme.annotations;
}
~~~

Meaning:

- `com.acme.annotations` must be present when compiling the `library` module.
- Readability of this module is propagated to modules that depend on `library`.
- The dependency remains optional at runtime.

This declaration is useful when types or annotations from the dependency appear in APIs or metadata that downstream modules need to see at compile time, while the runtime does not necessarily need that library.

Design carefully if a public API contains types from a `static` module. When the dependency is absent at runtime, classes referencing those types should not be loaded or used in a way that requires the missing module.

## 7. Complete Example with Two Named Modules

This example creates a library module `com.acme.greeter` and an application module `com.acme.app`. The application declares `requires` to use the API exported by the library.

Directory structure:

~~~text
module-demo/
  src/
    com.acme.greeter/
      module-info.java
      com/acme/greeter/api/Greeting.java
    com.acme.app/
      module-info.java
      com/acme/app/Main.java
~~~

### Library Module

File `src/com.acme.greeter/module-info.java`:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
~~~

File `src/com.acme.greeter/com/acme/greeter/api/Greeting.java`:

~~~java
package com.acme.greeter.api;

public class Greeting {
    public String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The module exports the `com.acme.greeter.api` package so other modules can use the `Greeting` class.

### Application Module

File `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.greeter.api.Greeting;

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.message("JPMS"));
    }
}
~~~

The `requires com.acme.greeter` directive allows `app` to read the library module; `exports` in `greeter`'s descriptor allows `app` to access the API package.

### Compiling

Run from the `module-demo` directory using JDK 17 or later:

~~~bash
javac --module-source-path src -d mods -m com.acme.greeter,com.acme.app
~~~

Explanation:

- `--module-source-path src` specifies the location of the source tree organized by module name.
- `-d mods` places the compiled modules into the `mods` directory.
- `-m` specifies the two modules to compile.

After compilation, the output structure looks like:

~~~text
mods/
  com.acme.greeter/
    module-info.class
    com/acme/greeter/api/Greeting.class
  com.acme.app/
    module-info.class
    com/acme/app/Main.class
~~~

### Running the Application

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello, JPMS!
~~~

The JVM locates the `app` module and its `greeter` dependency on the module path, resolves `requires`, and then invokes the specified main class.

## 8. Example of requires transitive

Suppose the `model` module provides the `Customer` type:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Customer(String name) {
}
~~~

The `library` module returns `Customer` in its public API:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
    exports com.acme.library.api;
}
~~~

~~~java
package com.acme.library.api;

import com.acme.model.api.Customer;

public class CustomerService {
    public Customer findCustomer() {
        return new Customer("Ada");
    }
}
~~~

The `app` module only needs to require `library`:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

In `app`, code can use `Customer` because `library` declared its dependency on `model` as `transitive`:

~~~java
package com.acme.app;

import com.acme.library.api.CustomerService;
import com.acme.model.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new CustomerService().findCustomer();
        System.out.println(customer.name());
    }
}
~~~

If `library` had only used a plain `requires com.acme.model`, `app` would have had to declare `requires com.acme.model` as well to read `Customer` directly. This is why `transitive` is appropriate when a dependency is part of a public API.

## 9. requires and the Module Graph

When compiling or running a modular application, the compiler/JVM builds a module dependency graph.

Example:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.library
    |
    | requires transitive
    v
com.acme.model
~~~

This graph shows which modules need to be resolved and which modules can read one another. Dependencies must be present on the module path or belong to the set of system modules provided by the runtime.

A required module that cannot be found can cause an error such as:

~~~text
java.lang.module.FindException:
Module com.acme.library not found
~~~

A module graph with an invalid dependency cycle can cause resolution to fail. For example, avoid designs like:

~~~text
module A requires B
module B requires A
~~~

The usual fix is to extract the shared API into a third module so that A and B both depend on the API module instead of depending cyclically on each other.

## 10. requires vs. Classpath and Module Path

`requires` belongs to JPMS's named module model. It is declared in `module-info.java` and processed when the compiler/JVM operates with the module path.

| Classpath | Module path |
|---|---|
| JARs/classes typically belong to the unnamed module | JARs/modules are treated as named or automatic modules |
| No `module-info.java` needed | Named modules typically have `module-info.class` |
| No `requires` directive to describe dependencies | `requires` describes dependency relationships |
| Package/module encapsulation is not the same as named modules | `exports` and `opens` control cross-module access |

A library placed on the classpath cannot be referenced by a `requires` directive as if it were already a named module. If it needs to be used on the module path, determine the JAR's module name. A JAR with `module-info.class` is an explicit module; a JAR without a descriptor can become an automatic module when placed on the module path.

An automatic module name can be derived from the JAR filename or specified via the `Automatic-Module-Name` attribute in the manifest. Because a derived name can change if the artifact is renamed, public libraries should generally declare a stable `Automatic-Module-Name` if they do not yet provide `module-info.class`.

## 11. Inspecting requires with JDK Tools

### Inspecting the Module Descriptor in a Class File

After compiling, use `javap` to view the descriptor:

~~~bash
javap -v mods/com.acme.app/module-info.class
~~~

In the output, look for the `Module` section. It contains the module name, `requires`, `exports`, `opens`, `uses`, and `provides`. The implicit `java.base` dependency may be marked `mandated`.

### Inspecting a Module in a JAR

If the module has been packaged into a JAR:

~~~bash
jar --describe-module --file app.jar
~~~

This command displays the module name and the directives stored in the module descriptor, or automatic module information.

### Checking Dependencies with jdeps

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

`jdeps` helps inspect the module descriptor and related dependencies. You can also list the module dependencies required for a JAR:

~~~bash
jdeps --print-module-deps app.jar
~~~

The result depends on the actual classes in the artifact and the provided module path. `jdeps` analyzes bytecode dependencies; it does not replace integration testing.

### Showing Runtime Resolution

~~~bash
java --show-module-resolution --module-path mods --module com.acme.app/com.acme.app.Main
~~~

The `--show-module-resolution` option displays information about resolved modules and their dependency relationships. It is useful when an application reports a missing module or picks up the wrong module version on the module path.

## 12. requires in JDK Platform Modules

JDK modules are divided by functionality. Some common module names:

| Module | Typical contents |
|---|---|
| java.base | Core APIs such as `java.lang`, `java.util`, `java.io` |
| java.sql | JDBC and database-related APIs |
| java.logging | Java Logging API |
| java.xml | XML, SAX, DOM, and XML APIs |
| java.desktop | AWT, Swing, and certain graphics APIs |
| java.net.http | HTTP Client API |
| java.management | JMX and JVM management APIs |

Example of a module using JDBC and logging:

~~~java
module com.acme.reporting {
    requires java.sql;
    requires java.logging;
}
~~~

Compiling and running require a JDK/runtime that includes the corresponding modules. If you build a custom runtime image with `jlink`, you must include the required modules in the image. You can list system modules with:

~~~bash
java --list-modules
~~~

A module that is not included in the runtime image cannot be resolved simply because the source has a `requires` directive. Ensure the image contains the necessary runtime dependencies.

## 13. Common Errors

| Error or symptom | Possible cause | Resolution |
|---|---|---|
| Module not found | Dependency is missing from the module path or module name is wrong | Check the artifact, module name, and `--module-path` |
| Package is not visible | Dependency module does not export that package | Check `exports` in the module descriptor |
| Module does not read another module | Missing required direct `requires` or `requires transitive` | Declare the proper dependency in the consuming module |
| Dependency compiles but fails at runtime | `requires static` is used, but runtime code still loads types from the dependency when it is absent | Isolate optional code and test both scenarios |
| Duplicate module / resolution error | Multiple versions of a module with the same name or conflicting module graph | Clean up the module path and unify dependencies |
| Circular dependence | Modules require each other | Extract shared API into an independent module |
| Automatic module name changes | Name is derived from the JAR filename | Declare a stable `Automatic-Module-Name` or use `module-info.java` |
| Reflection is blocked | Package is not opened to the framework needing reflection | Open only the needed packages using `opens` or controlled `--add-opens` |

When encountering errors, distinguish between module resolution errors, package access errors, and class loading errors. They occur at different stages and require different fixes.

## 14. Dependency Design Rules with requires

- Declare only the modules that the code actually depends on.
- Prefer plain `requires` for mandatory dependencies.
- Use `requires transitive` when a dependency is part of the public API and downstream modules need to read it.
- Use `requires static` for dependencies needed at compile time that may be absent at runtime.
- Avoid indiscriminate `requires transitive`, as it expands the consumer's module graph.
- Avoid dependency cycles; extract shared APIs into a separate module when needed.
- Do not confuse `requires` with `exports` or `opens`.
- Use stable module names and verify automatic module names of dependencies.
- Verify the actual module path in CI and runtime images.
- Only add `--add-reads` or options that break encapsulation when there is a specific compatibility reason; document and limit their scope.

A well-crafted module descriptor accurately expresses the module's dependency contract. When changing a public API, review `requires transitive` directives to avoid accidentally altering consumer readability.

## 15. Checklist for Using requires

- [ ] Identify the exact module name of the dependency.
- [ ] Place `requires` in `module-info.java` of the module that uses the dependency.
- [ ] Confirm the dependency is on the module path at compile time and runtime.
- [ ] Verify whether the needed packages are exported by the dependency.
- [ ] Use `requires transitive` only when the dependency is part of the API that consumers must read.
- [ ] Use `requires static` only when the code can operate safely if the dependency is absent at runtime.
- [ ] Verify the module graph has no cycles and no duplicate module names.
- [ ] Inspect the compiled descriptor with `javap` or `jar --describe-module`.
- [ ] Use `jdeps` and `--show-module-resolution` to investigate dependencies.
- [ ] Test on the actual runtime image, especially when using `jlink`.

## 16. Key Takeaways

- `requires` declares the modules that the current named module depends on and needs to read.
- Plain `requires` is a mandatory dependency at compile time and during runtime module graph resolution.
- `requires transitive` propagates readability of the dependency to modules that depend on the current module.
- `requires static` requires the dependency at compile time but allows it to be absent during runtime resolution.
- `requires static transitive` combines both behaviors.
- `requires` does not export packages; the providing module must declare `exports` separately.
- `java.base` is implicitly required by all normal named modules.
- Module name and dependency version are separate concepts; `requires` does not pin artifact versions.
- The module graph must be resolved on the module path; a missing dependency can cause `FindException`.
- Use `javap`, `jar`, `jdeps`, and `--show-module-resolution` to inspect module descriptors and dependency relationships.

## Official References

- [Java Language Specification — Module Declarations and Requires Directives](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html)
- [Java Virtual Machine Specification — Module Attributes](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [Module API — java.lang.module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html)
- [javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)