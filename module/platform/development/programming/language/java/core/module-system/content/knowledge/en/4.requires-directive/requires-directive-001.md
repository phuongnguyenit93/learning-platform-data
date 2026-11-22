# requires and Module Dependency Edges

In the Java Platform Module System (JPMS), a module declares a dependency using the `requires` directive in the `module-info.java` file. Each declaration creates a directed dependency relationship from the declaring module to the required module. The collection of these relationships forms a module dependency graph and is used by Java during compilation, module resolution, and application execution.

Properly understanding `requires` helps you know which modules must be present, which modules are read, why a dependency is propagated to clients, and how to troubleshoot errors when a module descriptor is missing or declares dependencies incorrectly.

## Objectives

After this lesson, you will be able to:

- Write and read the `requires` directive in `module-info.java`.
- Explain the direction of the dependency edge between a consuming module and a required module.
- Distinguish between `requires`, `requires transitive`, and `requires static`.
- Understand the role of dependencies in the module resolution process.
- Distinguish between a module reading another module and that module's packages being exported.
- Compile and run an example consisting of two named modules with a direct dependency relationship.

## 1. Syntax of requires

The `requires` directive is placed inside a module declaration:

~~~java
module com.acme.application {
    requires com.acme.logging;
}
~~~

In this example, `com.acme.application` is the module declaring the dependency, and `com.acme.logging` is the required module.

General syntax:

~~~java
requires [static] [transitive] module.name;
~~~

The two modifiers `static` and `transitive` are optional. They can be used individually or combined to specify how the dependency is processed and propagated to dependent modules.

Some basic rules:

- The name after `requires` is a module name, not a package name or a JAR file name.
- The required module must be findable in the corresponding module configuration, usually via the module path.
- A module cannot declare `requires` on itself.
- A module should declare only one requires relationship per module name.
- Dependency relationships between named modules must form an acyclic graph.
- Every named module, except `java.base`, reads `java.base` by default; therefore, it is usually unnecessary to write `requires java.base;`.

Module names are case-sensitive. The name used in `requires` must match the declared module name or the module name that Java determines for that dependency.

## 2. Directed Dependency Edges

Suppose module A uses an API provided by module B and declares:

~~~java
module A {
    requires B;
}
~~~

We can represent this relationship as follows:

~~~text
A  ──requires──>  B
    module A reads B
~~~

In this lesson, the arrow goes from the dependent module to the required module:

- A is the dependent module.
- B is a dependency of A.
- A has a direct readability relationship with B.
- B does not need to declare `requires A;` just because A depends on B.

This is a directed relationship. If A requires B, that does not mean B automatically reads A as well.

When there are multiple modules:

~~~text
com.acme.app ──requires──> com.acme.service
com.acme.app ──requires──> com.acme.logging
com.acme.service ────────> com.acme.model
~~~

The graph indicates that app depends directly on service and logging; service depends on model. Each module declares its own dependencies in its own module descriptor.

### 2.1. Direct requires does not automatically propagate readability

Suppose there are three modules:

~~~text
A ──requires──> B ──requires──> C
~~~

Module B declares `requires C;`, while A only declares `requires B;`.

In this case:

- B reads C because B declares a direct dependency.
- A reads B because A declares a direct dependency.
- A does not automatically read C just because B reads C.

If A's source code needs to reference types belonging to C, A must declare `requires C;` or B must expose dependency C using `requires transitive C;`.

This point distinguishes the **dependency graph** from the **set of modules that a module is allowed to read**. Module resolution may need to find and include C in the configuration because B depends on C, but that does not automatically create a readability relationship from A to C.

## 3. requires transitive: Propagating Dependencies to Clients

A module may use types from a dependency in its public API. When other modules depend on that API, they often also need to read the module containing the exposed types.

Example:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

The service module reads model and declares that relationship as transitive. Any module that reads service also receives a readability relationship to model.

Graph:

~~~text
com.acme.app ──requires──> com.acme.service
                                  |
                                  └──requires transitive──> com.acme.model
~~~

The app module only needs:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App can read both service and model. This is useful when service's public API uses types belonging to model, such as parameter types, return types, generic types, or parent interfaces.

You should not use `requires transitive` for every dependency. If a dependency only serves internal implementation and does not need to be read by clients, using regular `requires` keeps the dependency graph cleaner.

## 4. requires static: Compile-Time Only / Runtime-Optional Dependencies

The `static` modifier is used to declare a dependency that is mandatory during compilation but may be absent at runtime:

~~~java
module com.acme.tool {
    requires static com.acme.annotations;
}
~~~

This declaration is typically suitable for compile-time-only dependencies, such as an annotation library that the application does not need to use at runtime.

It is important to distinguish:

- At compile time, a module declared with `requires static` must still be found so the compiler can verify the dependency.
- At runtime, that dependency may be absent without being required as a mandatory runtime dependency.
- If executed code still attempts to load or use classes from the absent dependency, the application may encounter class loading or linkage errors.
- `requires static` does not mean that the dependency's packages are exported.

If both behaviors need to be combined, a module can declare a static and transitive dependency:

~~~java
module com.acme.api {
    requires static transitive com.acme.annotations;
}
~~~

Use this combination when a dependency both needs to be propagated in the readability relationship at compile time and may be unnecessary at runtime. Review how clients use the API to ensure that the absence of the dependency at runtime is valid.

## 5. How does module resolution use requires?

When compiling or running a modular application, Java needs to determine the set of modules that form the application configuration. This process is commonly called **module resolution**.

At a high level, Java performs the following steps:

1. Identifies the root modules to compile or run.
2. Finds the modules directly required in module descriptors.
3. Continues finding the dependencies of those newly found modules.
4. Checks module names, observability, and the validity of dependency relationships.
5. Builds the module configuration for compilation or execution.

For example, if app requires service and service requires model:

~~~text
Root module: app
       |
       v
     service
       |
       v
      model
~~~

Java needs to resolve both service and model to create a valid runtime configuration. However, model being resolved into the configuration does not mean app is always allowed to read model; the modifier of the requires relationship between service and model must be checked.

### 5.1. The module path provides where to find modules

Example of compiling a modular application:

~~~bash
javac --module-path libs -d out --module-source-path src -m com.acme.app
~~~

Example of running:

~~~bash
java --module-path "out;libs" -m com.acme.app/com.acme.app.Main
~~~

In the run command above, the semicolon is the module path separator on Windows. On Linux and macOS, use a colon:

~~~bash
java --module-path "out:libs" -m com.acme.app/com.acme.app.Main
~~~

The module path tells Java where to find observable modules. The `requires` directive tells Java which module needs which dependency. These two parts work together during resolution.

Placing a JAR in the `libs` directory does not automatically create a dependency relationship in the module descriptor. If the app module needs the logging module, app must still declare `requires com.acme.logging;`.

### 5.2. Observing the resolution process

You can ask the JVM to display module resolution information when running:

~~~bash
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
~~~

The displayed information helps identify the root modules and dependencies that the JVM resolved. This is a useful tool when a module is not found or the module configuration produces a different result than expected.

## 6. Complete Example: app requires service

Let's create two named modules:

- `com.acme.service` provides the `GreetingService` class.
- `com.acme.app` uses that class.

Directory structure:

~~~text
src/
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/GreetingService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### 6.1. The service module

File `src/com.acme.service/module-info.java`:

~~~java
module com.acme.service {
    exports com.acme.service.api;
}
~~~

File `src/com.acme.service/com/acme/service/api/GreetingService.java`:

~~~java
package com.acme.service.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Service exports the `com.acme.service.api` package so other modules can access public APIs in that package.

### 6.2. The app module

File `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.service.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Lan"));
    }
}
~~~

App declares `requires com.acme.service;` to read the service module. Service exports the package containing the needed class. These two conditions work together so app's source code can import and call `GreetingService`.

### 6.3. Compiling and running

From the directory containing `src`:

~~~bash
javac --module-source-path src -d out -m com.acme.service,com.acme.app
~~~

Run the application:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Lan
~~~

This example demonstrates a direct dependency edge from app to service. If app omits `requires com.acme.service;`, the compiler does not have the readability relationship needed for app to reference service's API.

## 7. requires does not replace exports

A common misconception is thinking that simply declaring `requires B;` allows module A to use every class of B. In reality, the two directives solve two different things:

| Directive | Meaning |
|---|---|
| `requires B;` | The current module reads module B and declares a direct dependency |
| `exports p;` in B | Exposes package p to other modules that read B |
| `exports p to A;` in B | Exposes package p only to module A |
| `opens p;` in B | Allows deep reflection on package p at runtime |

For example, app has declared:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

But if service does not export the `com.acme.service.api` package, app still cannot import classes in that package through regular Java APIs.

Conversely, service exporting a package does not automatically make app read service. App still needs the appropriate `requires` relationship.

Even when a module is readable and the package is exported, classes or members must still satisfy Java's access rules. A non-public top-level class does not become public just because the package is exported.

## 8. Dependency Cycles and Module Organization

Named modules must have an acyclic dependency graph. The following example is an invalid design:

~~~text
module A requires B
module B requires C
module C requires A
~~~

A dependency cycle prevents the modules from being resolved as a valid module graph. The compiler or module tool will report an error about cyclic dependence.

When encountering this situation:

1. Identify which module is cyclically depending back on the original module.
2. Find the shared API portion that the modules need.
3. Consider extracting that API or abstraction into a separate module.
4. Invert the dependency direction through interfaces or service providers when appropriate.
5. Keep module descriptors reflecting a clear dependency direction.

For example, if A and B both need an abstraction, that abstraction can be placed into module C:

~~~text
A ──requires──> C
B ──requires──> C
~~~

This approach eliminates the cyclic edge and helps modules depend on a shared contract.

## 9. Common Errors with requires

### Module not found

Java cannot find the required module.

Check:

- Whether the module name in `requires` is accurate.
- Whether the module path contains the directory or JAR providing the module.
- Whether the JAR is a module with a valid name or an automatic module.
- Whether the module being compiled/run receives the correct module path configuration.

### Package not visible despite requires

The consuming module reads the providing module, but the needed package has not been exported, or a qualified export is not aimed at the current module.

Check `exports` in the provider's module descriptor.

### Indirectly dependent module, but source code needs types from the dependency

If A requires B and B requires C with a regular `requires`, A does not automatically read C. Add `requires C;` in A or consider `requires transitive C;` in B if C is part of the API that B exposes.

### Dependency only needed at compile time

Consider `requires static` if the dependency is not mandatory at runtime and runtime code can operate when the dependency is absent.

### Cyclic dependence

Review dependency directions and extract shared abstractions if needed. Do not try to resolve a cycle by adding more `requires` directives.

## 10. Principles for Declaring Dependencies

- Declare dependencies directly in the module that actually uses them.
- Keep dependency edges unidirectional and avoid cycles.
- Use `requires transitive` when clients of the module need to read the dependency as part of the API contract.
- Use `requires static` when a dependency is only mandatory at compile time and may be absent at runtime.
- Do not declare transitive just to make compilation errors disappear; determine whether the dependency truly belongs to the public API.
- Combine `requires` with `exports`: one specifies which module is read, and the other specifies which package is exposed.
- Keep the module path consistent between compile time and runtime to avoid differing resolution configurations.

## 11. Self-Check

**Scenario 1:** Module A declares `requires B;`. In which direction is the dependency edge understood?

**Answer:** From A to B. A is the dependent module and B is the required module; A reads B.

**Scenario 2:** A requires B, and B requires C using a regular `requires C;`. Can A import classes from C solely through that relationship?

**Answer:** No. A reads B but does not automatically read C. A needs to declare a direct dependency on C, or B must use `requires transitive C;` if readability is meant to be propagated.

**Scenario 3:** Why must a dependency be present on the module path?

**Answer:** The module path is where Java looks for observable modules to resolve dependencies. The `requires` directive names the needed module, but does not itself supply the module file.

**Scenario 4:** The app module already has `requires com.acme.service;`, but the compiler does not allow importing a class in an internal package of service. What should be checked?

**Answer:** Check whether service exports that package and whether the type and its members have appropriate access levels. Readability does not replace package exports.

**Scenario 5:** A module only needs a dependency at compile time. Which modifier may be appropriate?

**Answer:** `requires static dependency;`, provided that runtime code does not need classes of the dependency when the dependency is absent.

**Scenario 6:** A requires B, and B requires A. Can this be solved by adding to the module path?

**Answer:** No. This is a dependency cycle in the named module graph. The dependency direction must be redesigned or a shared abstraction extracted.

When reading a module descriptor, treat each `requires` line as a directed edge: the current module depends on the named module. Then check modifiers, the module path, package exports, and the resolution configuration to fully understand how the dependency is used.