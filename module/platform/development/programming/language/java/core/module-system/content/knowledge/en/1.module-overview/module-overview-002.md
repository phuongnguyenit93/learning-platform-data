# Why the classpath needs a clearer module model

In small Java programs, the classpath is usually sufficient to include the necessary directories and JARs at compile time and runtime. As a project grows and multiple libraries and development teams become involved, the classpath reveals an important limitation: it tells the JVM **where to find classes**, but it does not clearly describe **which component depends on which component** and **which parts are allowed to be used**.

The Java Platform Module System (JPMS), introduced in Java 9, adds a model for declaring boundaries and dependency relationships between modules. This model makes application structure easier to read, control, and maintain.

## 1. What problem does the classpath solve?

The classpath is a list of directories and JAR files that the class loader can search when an application needs a class or resource. When running a program, we typically pass the classpath using the `-cp` or `-classpath` option.

Example:

```shell
java -cp "app.jar;lib/*" com.example.Main
```

On Windows, the separator between classpath entries is typically a semicolon; on Linux and macOS, it is a colon. The example above illustrates the idea: the application and its libraries are placed into a single search list.

The classpath is practical. You can add a JAR, swap a library, or run an application without declaring a new module structure. Tools like Maven and Gradle can also resolve dependencies and construct the appropriate classpath for compile or run tasks.

The problem arises when this list becomes the only way to describe the structure of a large system. At runtime, the classpath is essentially a flattened list. The JVM does not receive a complete description of each library's architectural intent.

## 2. Limitations of a flat classpath

### 2.1. Dependency relationships are not declared at component boundaries

Suppose an application has three parts:

- `catalog` manages the product catalog.
- `orders` creates and processes orders.
- `reports` aggregates data to generate reports.

Architecturally, `orders` may need to use the API of `catalog`, and `reports` may need to read data from both. However, when all JARs sit on the same classpath, classes can see one another much more broadly than the architecture intends.

If `orders` accidentally calls an internal implementation class of `catalog`, the classpath has no module rules to prevent it. The call may compile and run, even though it creates an unintended dependency.

This makes architectural boundaries heavily reliant on team conventions and source code organization. When someone changes the internal structure of a library, places that used internal classes can be broken.

### 2.2. Difficulty distinguishing public API from internal implementation

Java already has access modifiers `public`, `protected`, package-private, and `private`. However, these levels do not establish a module-level boundary.

A `public` class in a JAR can generally be used by other code on the classpath if the class is found and standard access conditions are met. Consequently, it is hard for a library to express:

- Which packages are supported API.
- Which packages serve only internal implementation.
- Which components are permitted deep access via reflection.

In large systems, this distinction matters greatly. If library consumers depend on internal classes, the library team will struggle to change implementation details without causing breaking changes.

### 2.3. Duplicate class names and lookup order can cause surprises

The classpath is ordered. If multiple entries contain the same fully qualified class name, the class loader may find one copy before the others according to its search order. The application may then run with a different version of the class than the developer expected.

This situation often occurs when:

- Two libraries package classes with the same fully qualified name.
- An old JAR remains on the classpath after upgrading a library.
- An application has multiple versions of transitive dependencies.
- Packages are split across multiple JARs without clear ownership conventions.

The issue is not limited to class names. Resource lookup can also be affected by classpath ordering. As a result, a configuration error can sometimes look like a logic bug in the program.

### 2.4. The classpath does not represent the dependency graph at runtime

Maven or Gradle may know direct dependencies, transitive dependencies, and selected versions. However, once the build tool constructs the classpath, most of that information has been reduced to a list of paths.

From this list, the JVM cannot easily tell:

- Which JAR is a direct dependency of which component.
- Which component actually needs a given library.
- Which packages should be exposed to other modules.
- Whether a dependency is being used outside architectural intent.

In other words, the build tool may understand the dependency graph, whereas the runtime classpath only represents a set of search locations. The two concepts are related, but not the same.

### 2.5. Difficulty controlling change in large systems

When component boundaries are not enforced, a small change can ripple across many other parts. An internal class becomes an informal dependency point; an old dependency lingers because no one is sure where it is still used; or two teams accidentally create packages with the same name.

These issues increase the cost of reading, refactoring, and upgrading code. They also make it harder to pinpoint the responsibility of each library.

## 3. What does the module model add?

JPMS introduces the concept of a **named module** to the Java platform. A module is a group of packages and resources with its own identity, accompanied by a description of its dependencies and exposed packages.

This description is usually written in a `module-info.java` file at the root of the module's source set. When compiled, this file becomes `module-info.class` in the artifact.

A module can declare:

- `requires`: modules that it needs to read and use.
- `exports`: packages exposed to other modules.
- `opens`: packages opened for deep reflection where necessary.
- `uses` and `provides`: service consumption and provision relationships via the ServiceLoader mechanism.
- `requires transitive`: dependencies that modules depending on the current module also need to be able to read.

For example, the catalog module can expose its API and keep its implementation internal:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

The orders module explicitly declares its dependencies:

```java
module com.example.orders {
    requires com.example.catalog;
    requires java.sql;

    exports com.example.orders.api;
}
```

From this description, a reader knows that `orders` depends on `catalog` and `java.sql`. Other modules can use public types in the `com.example.orders.api` package, but cannot automatically access unexported implementation packages.

### 3.1. Readability: which module is allowed to read which module?

A module does not automatically see every other module on the module path. It must declare dependencies using `requires`.

These declarations form the module graph. At startup, the system resolves the graph to determine the required modules and the readability relationships among them. If a required dependency cannot be resolved, the application can fail right at startup instead of only surfacing an error when a specific code branch is invoked.

`requires transitive` is useful when module A's API exposes data types belonging to module B. If module C depends on A, the transitive declaration allows C to read B through the relationship published by A.

### 3.2. Exports: which module is allowed to use which package?

`exports` exposes a package to other modules. This is the module-level API boundary.

For example, `com.example.catalog.api` can hold types needed by library consumers, while `com.example.catalog.internal` holds algorithms, adapters, or storage details. When an internal package is not exported, other modules cannot use public types in that package as ordinary API.

This organization establishes a clearer contract: module consumers rely on the exposed parts, while the development team has room to evolve the internal parts.

### 3.3. Opens: supporting reflection while preserving boundaries

Some frameworks require deep reflection to read or modify non-public members, such as when mapping objects, injecting dependencies, or serializing data.

`opens` allows opening a package for deep reflection. The opening scope can be broad or restricted to a specific module. This differs from `exports`: export exposes ordinary Java API, whereas open permits deep reflection within the declared scope.

Therefore, when migrating an application to JPMS, frameworks requiring reflection may need appropriate `opens` configuration. You should not open an entire module indiscriminately, as doing so diminishes the benefits of module boundaries.

## 4. How do the classpath and module path differ?

Both the classpath and the module path supply libraries to the execution process, but they represent two different models.

| Aspect | Classpath | Module path |
|---|---|---|
| Model | List of directories/JARs for class lookup | Set of modules with explicit identities and relationships |
| Dependency description | Not present in the flattened runtime classpath | Declared with `requires` |
| Package scope | No module-level export list | Declared with `exports` |
| Encapsulation | Primarily relies on Java access rules and classloaders | Adds module, export, and open boundaries |
| Legacy dependencies | JARs on the classpath operate under the classpath model | JARs without a descriptor can become automatic modules when placed on the module path |
| Structural checks | Many issues only surface when a class is loaded or a feature is called | The module graph is resolved at startup |

Classes loaded from the classpath belong to the unnamed module associated with the corresponding classloader. The unnamed module can read other modules, but named modules cannot declare `requires` directly on the unnamed module. Thus, when designing named modules, their dependencies must be provided as resolvable modules.

A JAR without `module-info.class` can still be placed on the module path as an **automatic module**. The module name can come from the `Automatic-Module-Name` attribute in the manifest; if absent, the name is derived from the JAR file name. Automatic modules help legacy libraries participate in migration, but do not provide fine-grained package boundaries like a module with an explicitly designed descriptor.

## 5. Example of API boundaries in an application

Suppose a sales application has the following structure:

```text
catalog/
└── src/main/java/
    ├── module-info.java
    └── com/example/catalog/
        ├── api/
        │   └── Product.java
        └── internal/
            └── ProductRepositoryImpl.java

orders/
└── src/main/java/
    ├── module-info.java
    └── com/example/orders/
        ├── api/
        │   └── OrderService.java
        └── internal/
            └── OrderServiceImpl.java
```

The `catalog` module exports only its API package:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

The `orders` module requires `catalog`:

```java
module com.example.orders {
    requires com.example.catalog;
    exports com.example.orders.api;
}
```

Then `orders` can use `Product` from the `catalog` API. It cannot rely on `ProductRepositoryImpl` in `catalog`'s internal package as an ordinary API.

If the development team later changes how products are stored, they can replace `ProductRepositoryImpl` without needing to maintain compatibility with modules that respected the public boundary. The module system turns architectural conventions into rules that compiler and runtime tools can enforce.

## 6. Does JPMS replace Maven or Gradle?

No. You must distinguish **build system modules** from **JPMS modules**.

Maven and Gradle manage projects, dependency artifacts, library versions, plugins, build tasks, and packaging. JPMS describes modules at the Java platform level: which modules exist, which module reads which module, and which packages are exposed.

A Gradle project can have multiple subprojects without every subproject needing its own JPMS module. Conversely, a build project can package or compile JPMS modules according to the structure the project chooses.

JPMS also does not replace a dependency manager. It does not fully handle selecting library versions, downloading artifacts from repositories, or managing transitive dependency mediation. Those tasks still belong to build tools. The module system adds structure and access rules for the modules that have been supplied.

## 7. The module model does not solve every problem

JPMS clarifies module-level boundaries and dependencies, but it is not a security sandbox mechanism for Java code. Modules still run within the same process and share that process's permissions. If an application needs to isolate untrusted code, another appropriate isolation architecture is required.

The module system also does not automatically fix package design, eliminate circular dependencies, or select compatible library versions. If modules are designed too large, export too broadly, or open every package for reflection, encapsulation benefits decrease significantly.

Therefore, JPMS should be viewed as a tool for expressing and enforcing architectural boundaries. It is effective when a team identifies its public APIs, valid dependencies, and implementation parts that need to remain hidden.

## 8. Migrating from the classpath to the module path

It is not necessary to migrate an entire application at once. A step-by-step roadmap is usually easier to control:

1. **Inventory dependencies:** identify direct JARs, transitive dependencies, duplicate packages, and internal JDK APIs currently in use.
2. **Stabilize module names:** for libraries without a descriptor, `Automatic-Module-Name` can be declared in the manifest so the module name does not depend on how the JAR file is named.
3. **Clarify packages:** resolve packages shared across multiple libraries and decide which packages are API and which are internal implementation.
4. **Add descriptors:** create `module-info.java`, declare truly required dependencies with `requires`, and export only packages that need to be public.
5. **Configure frameworks:** open the right packages with `opens` when frameworks need deep reflection.
6. **Check JDK dependencies:** `jdeps --jdk-internals` can be used to find usage of internal JDK APIs and plan replacements.
7. **Use transitional options when needed:** `--add-reads`, `--add-exports`, and `--add-opens` can help an application migrate gradually, but should be treated as scoped transitional measures.

The classpath is still supported by Java. A small application, internal tool, or legacy system can continue using the classpath if the current model fits. The value of JPMS is clearer when a project needs stable API boundaries, coordination across many components, and module-level dependency control.

## 9. When should you care about the module model?

The module model is especially useful when:

- An application has many libraries or multiple teams developing together.
- Internal packages are frequently accessed from the outside.
- Dependencies between components are hard to track.
- Upgrading a library frequently breaks unrelated components.
- The team wants to publish a stable API while retaining the freedom to change the implementation.
- The application needs explicit control over which packages are opened for reflection.

For a small program with only a few JARs and few architectural boundaries, the classpath may remain a simple, reasonable choice. There is no need to add a module descriptor just because a project uses modern Java. Choose JPMS when those boundaries bring real value to how the system is organized and maintained.

## Conclusion

The classpath helps Java locate classes from directories and JARs, but it does not fully express dependency structure and access permissions between components. As a system grows, a flat classpath list makes public APIs, internal implementation, and dependency relationships easy to blur.

JPMS adds named modules, explicit dependencies, package exports, and mechanisms to open packages for reflection. As a result, architecture is described directly in the source code and can be checked during compilation, module resolution, and application execution.

The key point is: the classpath answers the question "where does the JVM find classes?", while the module model also answers "which component needs which component, and which parts are allowed to be used?".