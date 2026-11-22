# requires transitive in the Java Module System

## 1. What is requires transitive?

The Java Platform Module System (JPMS), introduced in Java 9, organizes applications into named modules, declares dependencies, and specifies which packages can be accessed by other modules. Each named module typically has a **module-info.java** file to declare the module name, dependencies, and exported packages.

In a module descriptor, the **requires** directive declares that a module needs to read another module. The **transitive** modifier extends that readability to modules that depend on the current module.

Syntax:

~~~java
module com.example.facade {
    requires transitive com.example.api;
}
~~~

When another module declares:

~~~java
module com.example.app {
    requires com.example.facade;
}
~~~

then `com.example.app` can read both `com.example.facade` and `com.example.api`. The reason is that `com.example.facade` declared the `com.example.api` dependency using `requires transitive`.

In other words, **requires transitive propagates readability of a dependency through the required module**. It is especially useful when a module's public API uses data types belonging to another module.

## 2. Readability in JPMS

JPMS distinguishes between a module **reading** another module and a package being **exported** to other modules.

- **Readability** indicates whether the current module can reference types provided by another module.
- **Exports** determines which packages of a module can be accessed by other modules.
- **Requires** creates a readability relationship between modules.
- **Requires transitive** creates a readability relationship for the current module and propagates that readability to modules that read the current module.

Suppose there are three modules:

~~~text
com.example.app
       |
       | requires
       v
com.example.facade
       |
       | requires transitive
       v
com.example.api
~~~

`com.example.facade` reads `com.example.api` to use its API. Because the dependency is marked `transitive`, `com.example.app` also reads `com.example.api` when it only declares `requires com.example.facade`.

Readability is propagated along transitive edges in the module graph. If a module reads A, and A declares `requires transitive B`, that module also reads B. If B further declares `requires transitive C`, readability can continue to propagate to C. A regular dependency of B is not automatically propagated further.

## 3. Distinguishing requires and requires transitive

Both directives allow the declaring module to read the dependency. The difference lies in the readability of downstream modules.

| Directive | Declaring module reads dependency | Module reading the current module automatically reads dependency? |
|---|---|---|
| requires B | Yes | No |
| requires transitive B | Yes | Yes |
| requires static B | Yes at compile time; optional at runtime | No |
| requires static transitive B | Yes at compile time; optional at runtime | Yes at compile time |

Example facade module:

~~~java
module com.example.facade {
    requires com.example.api;
    exports com.example.facade;
}
~~~

The `facade` module reads `com.example.api`, but an `app` module that only declares `requires com.example.facade` does not automatically read `com.example.api`. If the `app` source code imports a type from the `com.example.api` package, the compiler reports that the package is not read by the `app` module.

Changing it to:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

allows the `app` module to read `com.example.api` through `facade` without needing to declare an additional `requires com.example.api`.

If `app` intentionally depends directly on the `com.example.api` API beyond the portion exposed by `facade`, `app` can still declare `requires com.example.api` explicitly to express its own architectural dependency.

## 4. When should you use requires transitive?

Consider `requires transitive` when a dependency's data type appears in the public API that the current module provides to clients.

Typical cases:

- A public method returns a type defined in the dependency module.
- A public method accepts a parameter belonging to the dependency module.
- A public class extends a class or implements an interface from the dependency.
- A public generic type uses a dependency type in a type parameter or type bound.
- A record, annotation, or public API signature requires a type from the dependency for clients to compile and use it.

For example, `facade` provides a method:

~~~java
public ApiType create() {
    return new ApiType("v1");
}
~~~

The client uses the `ApiType` result. If `facade` only declares `requires com.example.api`, the client will not have readability to the module containing `ApiType`. `requires transitive` expresses that the dependency is part of the API contract provided by `facade`.

If the dependency is only used internally for implementation—such as a private class or an internal call that does not appear in the public API—a regular `requires` directive is usually more appropriate.

You should not mark every dependency as `transitive`. Doing so increases the number of modules clients must read, expands the dependency surface, and can turn implementation details into part of the public contract.

## 5. requires transitive does not replace exports

A module can read another module and still be unable to access an unexported package.

Example API module:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

The `com.example.api` package is exported, so modules reading `com.example.api` can access public types in that package.

If the `facade` module declares:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

then two things happen independently:

- `com.example.facade` exports the `com.example.facade` package to clients.
- `com.example.facade` propagates readability to `com.example.api`.

`requires transitive` does not export the `com.example.api` package on behalf of the module that owns that package. The `com.example.api` module must still export the required package.

A qualified export can be used:

~~~java
module com.example.api {
    exports com.example.api to com.example.facade;
}
~~~

This exports the package only to the listed modules. A downstream client such as `com.example.app` can read `com.example.api` thanks to `requires transitive`, yet still cannot access the package if it is exported exclusively to `com.example.facade`.

Distinguish between three questions:

1. Does the client module read the API module?
2. Does the API module export the package containing the required type?
3. Do the accessed type and member have sufficient public/protected visibility for the context?

Both readability and package accessibility must be satisfied.

## 6. Complete example with three Java 17 modules

The following example has three modules:

- **com.example.api** provides the `ApiType` type.
- **com.example.facade** uses `ApiType` in its public API and declares `requires transitive`.
- **com.example.app** only declares `requires com.example.facade` yet can still use `ApiType`.

Directory structure:

~~~text
project/
  src/
    com.example.api/
      module-info.java
      com/example/api/ApiType.java
    com.example.facade/
      module-info.java
      com/example/facade/Facade.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  mods/
~~~

### Module 1: com.example.api

File `src/com.example.api/module-info.java`:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

File `src/com.example.api/com/example/api/ApiType.java`:

~~~java
package com.example.api;

public final class ApiType {
    private final String value;

    public ApiType(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
~~~

This module exports the `com.example.api` package so other modules can use the `ApiType` class.

### Module 2: com.example.facade

File `src/com.example.facade/module-info.java`:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

File `src/com.example.facade/com/example/facade/Facade.java`:

~~~java
package com.example.facade;

import com.example.api.ApiType;

public class Facade {
    public ApiType create() {
        return new ApiType("v1");
    }
}
~~~

`Facade` uses `ApiType` in the return type of a public method. `requires transitive` indicates that clients reading `facade` also need permission to read the API module to compile and use this type.

### Module 3: com.example.app

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.facade;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.facade.Facade;
import com.example.api.ApiType;

public class Main {
    public static void main(String[] args) {
        ApiType api = new Facade().create();
        System.out.println("API value: " + api.value());
    }
}
~~~

Note that the `app` module does not declare `requires com.example.api`. It reads that module through the `requires transitive` directive in the `facade` module.

### Compiling all three modules

Run from the `project` directory:

~~~bash
javac --release 17 -d mods --module-source-path src \
    -m com.example.api,com.example.facade,com.example.app
~~~

The compiler places the compiled modules into the `mods` directory.

### Running the application

~~~bash
java --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Exact output:

~~~text
API value: v1
~~~

This example demonstrates that the `app` module can import `ApiType` even though `app`'s `module-info.java` only declares `requires com.example.facade`.

## 7. Removing transitive to observe the difference

In `com.example.facade`'s `module-info.java`, replace:

~~~java
requires transitive com.example.api;
~~~

with:

~~~java
requires com.example.api;
~~~

Recompile all three modules using the `javac` command from the previous section. The `app` module will report an error similar to:

~~~text
package com.example.api is not visible
(package com.example.api is declared in module com.example.api,
 but module com.example.app does not read it)
~~~

The cause is that `facade` still reads `api`, but that readability relationship is not propagated to `app`.

There are two ways to fix this depending on your design intent:

**Option 1: Keep `requires transitive` in `facade`.** Use this when `ApiType` is genuinely part of the public API that `facade` wants to provide to clients.

**Option 2: Keep a regular `requires` in `facade` and add a direct dependency to `app`.** Update `app`'s `module-info.java`:

~~~java
module com.example.app {
    requires com.example.facade;
    requires com.example.api;
}
~~~

This option is appropriate when `app` intentionally depends on both modules and `facade` does not want to expose the `api` dependency as part of its contract.

## 8. requires static transitive

JPMS allows combining the `static` and `transitive` modifiers:

~~~java
module com.example.annotations {
    requires static transitive com.example.annotation.api;
}
~~~

The **static** modifier indicates a dependency required at compile time that may be absent at runtime. The **transitive** modifier still specifies that modules reading the current module also need readability to the dependency in a compile-time context.

You can consider this form for optional compile-time-only dependencies, such as annotation types or metadata that the application does not need to execute its main flow.

However, if a dependency's type appears in the public API and clients actually need to load or invoke it at runtime, the dependency must be present at runtime. If the module is missing, operations requiring that type can fail during class loading or linking. Therefore, only use `static` when the dependency can genuinely be absent at runtime by design.

Comparison:

- **requires transitive B**: B is a mandatory dependency in the module graph.
- **requires static transitive B**: B is required at compile time and its readability is propagated to clients; B may not be required at runtime if it is absent and not needed by the actual execution path.

Do not use `static` to avoid packaging a mandatory dependency.

## 9. Inspecting module descriptors and the module graph

You can use JDK tools to verify which directives have been recorded in a module descriptor.

After compiling the `facade` module, package it into a JAR:

~~~bash
jar --create --file mods/com.example.facade.jar \
    -C mods/com.example.facade .
~~~

View the module description:

~~~bash
jar --describe-module --file mods/com.example.facade.jar
~~~

The key output looks like:

~~~text
com.example.facade
exports com.example.facade
requires com.example.api transitive
requires java.base mandated
~~~

The line `requires com.example.api transitive` confirms that the modifier is present in the module descriptor.

You can ask the launcher to display the module resolution process at startup:

~~~bash
java --show-module-resolution --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

The output shows the resolved modules and their dependency relationships during startup. This is helpful when the module path contains many JARs or when a module cannot be found.

If you need to analyze application dependencies, the `jdeps` tool can also help inspect referenced modules:

~~~bash
jdeps --module-path mods --check com.example.facade
~~~

The results should be read alongside the module descriptor and source structure; `jdeps` analyzes dependencies used by bytecode, whereas `requires transitive` expresses the declared readability policy.

## 10. Relationship with Maven and Gradle

`requires transitive` belongs to JPMS and is recorded in `module-info.class`. Build tools have their own dependency systems, so the two mechanisms should not be treated as identical.

With the Gradle Java Library Plugin:

- An **api dependency** is placed on the consumer's compile classpath.
- An **implementation dependency** serves only the library's implementation and is not exposed on the consumer's compile classpath.

If a modular library exposes a type from dependency B in its API, the build design typically needs to expose B as an API dependency. In `module-info.java`, `requires transitive B` represents the corresponding readability relationship in JPMS.

With Maven, dependency scopes and artifact packaging affect which dependencies are propagated to consumers. The module descriptor still needs to declare `requires transitive` if you want JPMS to propagate readability to downstream modules.

Check both configuration layers:

1. Does the build tool provide the dependency JAR on the compile/runtime classpath or module path?
2. Does `module-info.java` declare the right `requires`, `requires transitive`, or `requires static`?

A correct directive in `module-info.java` neither downloads dependencies automatically nor packages dependencies into a JAR.

## 11. Common errors and how to handle them

### Package is not visible or module does not read it

Common causes:

- The client module has not declared `requires` on the module containing the package.
- An intermediate module uses a regular `requires` even though its public API includes a type from the dependency.
- The dependency has not been resolved on the module path.

How to handle: identify which module contains the failing type; inspect the `requires` chain; use `requires transitive` on the intermediate module if the dependency belongs to its public API, or declare `requires` directly in the client if the client has its own dependency.

### Module is read, but the package is still inaccessible

Readability is present, but the module owning the package has not exported that package, or only exported it to another module via a qualified export. Check `exports` in the `module-info.java` of the module containing the package.

### Using requires transitive for every dependency

Propagating readability unnecessarily exposes additional module dependencies and creates coupling for clients. Use it only when the dependency is a necessary part of the public API or when the module contract intentionally requires clients to read that dependency.

### Missing module at runtime

Check the module path and verify that dependencies are packaged. `requires transitive` does not automatically bundle dependency JARs with the application. If using `requires static`, confirm that runtime code paths genuinely do not require the optional module.

### Dependency cycle

JPMS does not allow dependency cycles between named modules. If A requires B and B requires A, the module graph cannot be resolved validly. Extract the shared API into a separate module or adjust the dependency direction.

### Confusing exports with requires transitive

`exports` opens a package of the module that owns that package. `requires transitive` propagates readability to a dependency module. The two directives solve different problems and often need to be combined when building modular APIs.

## 12. Design principles and checklist

When deciding whether to use `requires transitive`, ask yourself:

- [ ] Does the dependency appear in the module's public/protected API signatures?
- [ ] Do clients need to read the dependency to use the current module's API?
- [ ] Has the module owning that type exported the appropriate package?
- [ ] Is the dependency truly mandatory at runtime, or can it be `static`?
- [ ] Does `requires transitive` expose unnecessary implementation details?
- [ ] Does the build tool provide the dependency properly on the compile/runtime module path?
- [ ] Does the example or application compile when the client only requires the `facade` module?
- [ ] Have you inspected the module descriptor with `jar --describe-module`?
- [ ] Have you verified runtime module resolution with `--show-module-resolution`?

Use `requires transitive` to describe dependencies that clients need to read through the current module's public API. Use a regular `requires` for internal-only dependencies. Combine it properly with `exports` to ensure clients can both read the module and access the required packages.
