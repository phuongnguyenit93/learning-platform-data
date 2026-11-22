# Readability edges and accessible packages

In the Java Platform Module System (JPMS), one module can depend on another module, yet that alone is not enough for every package of the depended-upon module to be accessible. When analyzing a module graph, two concepts must be separated:

- **Readability edge:** the relationship indicating which module can read types provided by which module. This relationship is formed primarily from the `requires` directive.
- **Accessible package:** a package that the calling module is permitted to access across the module boundary. The module containing the package must export that package to the calling module, and the type and member must still satisfy Java access modifiers.

An API call between two named modules is valid only when the calling module reads the providing module, the package containing the API is exported to the calling module, and the type/member has appropriate visibility. Readability and package accessibility are two separate conditions; both must be checked when troubleshooting module errors.

## 1. Readability edges in the module graph

The module graph describes the resolved modules and the dependency relationships among them. When module `com.acme.app` declares:

```java
module com.acme.app {
    requires com.acme.library;
}
```

JPMS creates a readability relationship from `com.acme.app` to `com.acme.library`. You can visualize the edge in the graph:

```text
com.acme.app  ──requires──>  com.acme.library
```

This allows code in `com.acme.app` to reference types belonging to module `com.acme.library`, provided the packages of those types are exported appropriately. `requires` does not make every package of the library part of the public API.

The module graph is constructed when the compiler or runtime resolves modules. If a required dependency is missing from the module path or cannot be resolved, compilation or startup will fail before the application uses the API.

## 2. Readability is not synonymous with accessibility

Suppose a library module has a public class:

```java
package com.acme.internal;

public class InternalClient {
    public void connect() {
        System.out.println("Connected");
    }
}
```

The library's descriptor:

```java
module com.acme.library {
}
```

The application's descriptor:

```java
module com.acme.app {
    requires com.acme.library;
}
```

The application already reads the library module because there is a `requires` edge. However, the package `com.acme.internal` is not exported. Therefore, the application cannot import `InternalClient`, even though both the class and the method are `public`.

You can check using two independent questions:

1. **Readability:** does the calling module read the module containing the class?
2. **Package accessibility:** does the module containing the class export that package to the calling module?

If readability is missing, check `requires` and module resolution. If readability is already present yet the package is still inaccessible, check `exports`, qualified exports, and access modifiers.

## 3. Conditions for a package to become accessible

For another named module to use an API, the following main conditions must be satisfied:

1. The module containing the package has been resolved in the module graph.
2. The calling module reads the module containing the package.
3. The package is exported unconditionally or exported conditionally to that exact calling module.
4. The accessed type is public; the constructor and member being invoked must also have appropriate visibility.
5. Types appearing in the API signature must also be accessible according to the corresponding rules.

For example, library descriptor:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Application descriptor:

```java
module com.acme.app {
    requires com.acme.library;
}
```

If `com.acme.api.Client` is public, the application can import and use it. Other packages such as `com.acme.library.internal` remain closed if not exported.

Accessibility conditions are determined at the package level. The `exports` directive cannot export only a single individual class within a package; if a package is exported, the public types in that package can become part of the API.

## 4. Unqualified export and qualified export

An unqualified export allows every module that reads the providing module to access the package:

```java
module com.acme.library {
    exports com.acme.api;
}
```

A qualified export permits only the specified modules:

```java
module com.acme.library {
    exports com.acme.spi to com.acme.app, com.acme.testkit;
}
```

If `com.acme.other` declares `requires com.acme.library;` but is not in the target list, that module still cannot access `com.acme.spi`. The readability edge exists, yet the package is not accessible to that module.

This is useful when a library has an internal API dedicated to specific collaborating modules, such as the main application or a test kit. For public APIs meant for many consumers, an unqualified export is usually more appropriate.

## 5. Readability extended by requires transitive

A module may need to expose its dependency to downstream modules. The `requires transitive` directive creates a transitive readability relationship.

Suppose the graph has three modules:

```text
com.acme.app  ──requires──>  com.acme.facade
                                  |
                                  └──requires transitive──> com.acme.api
```

Descriptor of facade:

```java
module com.acme.facade {
    requires transitive com.acme.api;
    exports com.acme.facade;
}
```

Descriptor of application:

```java
module com.acme.app {
    requires com.acme.facade;
}
```

Because `com.acme.facade` declares `requires transitive com.acme.api`, a module that reads facade also reads `com.acme.api`. Therefore, application code can use API types in that dependency when the corresponding packages are exported.

`requires transitive` does not automatically export packages of the facade module, nor does it automatically export packages of the dependency. It only extends readability. Package accessibility is still determined by the module that owns the package.

Use `requires transitive` when a dependency appears in the module's public API, such as a return type or parameter of a public API belonging to the dependency module. Do not use it merely to make the graph wider; each transitive edge increases the dependencies that downstream modules must see.

## 6. requires static and environment-dependent readability

`requires static` declares a dependency that must be present at compile time but may not need to be present in the runtime image:

```java
module com.acme.tooling {
    requires static com.acme.annotations;
}
```

This is commonly used for annotations or supporting tools needed only during compilation. The module must have that dependency at compile time, whereas at runtime the dependency might not be included in the runtime configuration.

If the required module is actually present in the runtime configuration, the readability relationship is applied according to the runtime module graph. Therefore, when analyzing errors, distinguish between the compile-time graph and the runtime graph. Do not assume every `requires static` dependency is always present when running.

Two modifiers can be combined:

```java
module com.acme.tooling {
    requires static transitive com.acme.annotations;
}
```

This combination makes the dependency transitive at compile time while remaining optional at runtime. Use it only when the API contract and distribution model genuinely require that behavior.

## 7. java.base and default readability relationships

Every ordinary named module reads `java.base`. If the source descriptor does not write `requires java.base;`, the compiler adds this mandatory dependency to the compiled module descriptor.

Example:

```java
module com.acme.app {
}
```

The module can still use `String`, `Object`, `List`, and many core APIs because those APIs belong to `java.base`. This is the foundational dependency mandated by JPMS.

However, not every JDK module is automatically readable. If an application uses JDBC, logging, or the HTTP Client, it needs to declare the corresponding dependencies, for example:

```java
module com.acme.reporting {
    requires java.sql;
    requires java.logging;
}
```

Readability to `java.base` does not automatically create readability to `java.sql` or `java.logging`.

## 8. Accessible packages differ from deep reflection

`exports` allows access to public types under standard Java rules. It does not automatically grant deep access to private fields or methods via reflection.

If a framework needs deep reflection, the package must be opened:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
```

In this example, consumers can use public APIs belonging to `com.acme.domain.api`; the ORM module can perform deep reflection on the entity package. `opens` does not replace `exports` when Java code needs to import public types at compile time.

Both states can be checked using runtime APIs:

```java
Module source = Client.class.getModule();
Module caller = Main.class.getModule();

boolean exported = source.isExported("com.acme.api", caller);
boolean opened = source.isOpen("com.acme.entity", caller);

System.out.println("Exported: " + exported);
System.out.println("Opened: " + opened);
```

The two checks answer two different questions. If normal API access is unavailable, inspect `isExported`; if deep reflection is denied, inspect `isOpen`.

## 9. Example of a graph with readability but missing accessible packages

Suppose the module graph has:

```text
com.acme.app  ──requires──>  com.acme.library
```

Library descriptor:

```java
module com.acme.library {
    exports com.acme.api;
}
```

The library has two classes:

```java
package com.acme.api;

public class PublicClient {
}
```

```java
package com.acme.internal;

public class InternalClient {
}
```

The application can import `com.acme.api.PublicClient`, but cannot import `com.acme.internal.InternalClient`. Both classes are public and the app module reads the library module, yet only package `com.acme.api` is exported.

If the library descriptor is changed to:

```java
module com.acme.library {
    exports com.acme.api;
    exports com.acme.internal to com.acme.app;
}
```

then the internal package also becomes accessible to `com.acme.app`, while not being exposed publicly to other modules. This example shows that the module graph only describes readability; to know whether a calling module can use a specific package, you must check the package's export targets.

## 10. Tools for diagnosing the module graph and packages

You can inspect a JAR's descriptor:

```shell
jar --describe-module --file library.jar
```

To observe module resolution at runtime:

```shell
java --show-module-resolution \
    --module-path mods \
    --module com.acme.app/com.acme.app.Main
```

The `jdeps` tool helps inspect dependencies and modules:

```shell
jdeps --module-path mods --check com.acme.app
```

When troubleshooting access errors, read the results in order:

- Is the module containing the package actually in the module graph?
- Does the calling module have a readability edge to the providing module?
- Is the package exported, and if it is a qualified export, is the calling module in the list?
- Do the accessed type and member have appropriate visibility?
- Does a framework need deep reflection, and has the package been opened to the right module?

If the module is not resolved, fix the module path or dependencies first. If the module is already readable yet the package is not accessible, fix `exports` appropriately. If only deep reflection fails, check `opens` instead of widening the public API.

## 11. Design principles

- Use `requires` to declare dependencies and establish readability edges.
- Use `exports` to publish packages containing public APIs.
- Use qualified exports when a package is intended only for specific identified modules.
- Keep implementation packages unexported to avoid turning internal details into a public contract.
- Use `requires transitive` when a dependency is part of the downstream public API.
- Use `requires static` for dependencies needed at compile time that can be optional at runtime.
- Use `opens` specifically for deep reflection needs; do not confuse it with API accessibility.
- Inspect the actual module descriptors and graph when errors only occur on the module path.

Readability answers which module can read which module. Package accessibility answers whether a calling module is permitted to use a specific package. Distinguishing these two concepts helps read the module graph accurately and fix access errors at the right layer of JPMS.