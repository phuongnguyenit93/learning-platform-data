# Distinguishing requires from import in Java Code

In Java, both `requires` and `import` frequently appear when a piece of code needs to use a component defined elsewhere. Consequently, these two keywords are easily mistaken for two ways of declaring the same kind of dependency. In reality, they operate at two different levels:

- `requires` is a directive in `module-info.java`, declaring a readability relationship between modules in the Java Platform Module System (JPMS).
- `import` is a declaration in a Java compilation unit, allowing source code to reference types or members by shorter names.

A module may need both: `requires` to be permitted to read the module containing the API, and `import` to use class names in source code without writing fully qualified names everywhere.

## 1. What is requires?

`requires` is a directive in a module declaration. It appears inside `module-info.java` and declares that the current module depends on another module.

For example, the orders module needs to use the API of the catalog module:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

This declaration tells the module system that `com.example.orders` needs to read `com.example.catalog`. That relationship is used during compilation and when Java resolves the module graph at modular application launch.

`requires` does not point to a specific class. It declares a dependency at the module level. The required module must still expose the appropriate packages using `exports` if other modules need to access APIs in those packages.

Some common variants:

```java
module com.example.orders {
    requires com.example.catalog;
    requires transitive com.example.money;
    requires static com.example.annotations;
}
```

- `requires`: declares a regular dependency.
- `requires transitive`: exposes readability to the dependency for modules that read the current module; useful when the current module's API exposes types belonging to that dependency.
- `requires static`: a dependency needed at compile time but not mandatory at runtime solely because this directive is declared.

Every named module reads `java.base` implicitly, so there is normally no need to write `requires java.base;`.

## 2. What is import?

`import` is a declaration at the top of a Java source file. It allows using the simple name of a type or member instead of having to write the fully qualified name at every location.

Example without import:

```java
public class OrderService {
    public com.example.catalog.api.Product findProduct(String id) {
        return new com.example.catalog.api.Product(id);
    }
}
```

With import:

```java
import com.example.catalog.api.Product;

public class OrderService {
    public Product findProduct(String id) {
        return new Product(id);
    }
}
```

Both approaches reference the same `com.example.catalog.api.Product` type. The `import` declaration makes the code shorter and easier to read; it does not create a new module dependency.

Java has common forms of import:

**Importing a specific type**

```java
import java.util.List;
import java.util.Map;
```

**Importing types in a package with a wildcard**

```java
import java.util.*;
```

Wildcard imports do not recurse into subpackages. For example, `import java.util.*;` does not import types belonging to `java.util.concurrent`.

**Static import**

```java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;
```

Afterward, `PI` and `sqrt(25)` can be used directly in source code. Static imports also only affect how names are written in the compilation unit, not declaring a module dependency.

## 3. Differences in location and scope of impact

| Criterion | `requires` | `import` |
|---|---|---|
| Location | In `module-info.java` | In a regular Java source file |
| Level | Module | Compilation unit |
| Purpose | Declares that the current module needs to read another module | Allows referencing types or members by short names |
| Target | A named module | A type, nested type, or static member |
| Affects module graph | Yes | No |
| Grants package access | Establishes readability; the package still needs to be exported appropriately | Does not grant package access |
| Interchangeable? | No | No |

A concise way to remember:

- `requires` answers: **Which modules does my module need to read?**
- `import` answers: **In this source file, which type or member names do I want to write more concisely?**

The two questions are related, but they are not the same question.

## 4. Example combining requires and import

Suppose there are two modules:

- `com.example.catalog` provides the `Product` type.
- `com.example.orders` uses `Product` to create orders.

Simple structure:

```text
catalog/
└── src/
    └── com.example.catalog/
        ├── module-info.java
        └── com/example/catalog/api/Product.java

orders/
└── src/
    └── com.example.orders/
        ├── module-info.java
        └── com/example/orders/OrderService.java
```

### Step 1: The catalog module exposes its API

File `catalog/module-info.java`:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

File `Product.java`:

```java
package com.example.catalog.api;

public record Product(String id, String name) {
}
```

The `exports` directive allows other modules to access public types in the `com.example.catalog.api` package.

### Step 2: The orders module declares the dependency

File `orders/module-info.java`:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

The `requires` directive creates a readability relationship from orders to catalog. The orders module can use the packages exposed by catalog, subject to normal Java access rules.

### Step 3: Orders source code imports the Product type

File `OrderService.java`:

```java
package com.example.orders;

import com.example.catalog.api.Product;

public class OrderService {
    public String describe(Product product) {
        return "Order for " + product.name();
    }
}
```

Here the two declarations have separate roles:

- `requires com.example.catalog;` resides in the orders module descriptor, declaring the module relationship.
- `import com.example.catalog.api.Product;` resides in `OrderService.java`, enabling the source code to use the short name `Product`.

If the source code uses the fully qualified name, the import can be omitted:

```java
package com.example.orders;

public class OrderService {
    public String describe(com.example.catalog.api.Product product) {
        return "Order for " + product.name();
    }
}
```

However, the orders module still needs `requires com.example.catalog;` because source code of a named module must still have readability to the module containing the type being used.

## 5. Why does import not replace requires?

Try removing the `requires` directive from orders' `module-info.java` while keeping the import:

```java
module com.example.orders {
}
```

In the source code:

```java
import com.example.catalog.api.Product;

public class OrderService {
    Product find() {
        return null;
    }
}
```

If `com.example.catalog` is on the module path and is a named module, the orders module has not declared a readability relationship to it. An import cannot create that relationship by itself. The compiler may report an error stating that the package belonging to another module is not visible because the current module does not read that module.

Conversely, if `requires com.example.catalog;` is present without writing an import, the orders module still has readability to catalog. We just need to use the fully qualified name:

```java
package com.example.orders;

public class OrderService {
    com.example.catalog.api.Product find() {
        return null;
    }
}
```

This shows:

- Having an import does not equate to having module readability.
- Having requires does not equate to having imported a specific type.
- Both declarations may be needed together in a modular program.

## 6. Why does requires not replace import?

`requires` only declares the module that the current source code can read. It does not bring the class names in that module into the namespace of every Java file.

Example:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

In `OrderService.java`, we still need one of the following two ways to use the `Product` type.

Approach 1: use import:

```java
import com.example.catalog.api.Product;

public class OrderService {
    Product find() {
        return null;
    }
}
```

Approach 2: use the fully qualified name:

```java
public class OrderService {
    com.example.catalog.api.Product find() {
        return null;
    }
}
```

If you only write:

```java
public class OrderService {
    Product find() {
        return null;
    }
}
```

without importing `Product` and without a matching `Product` type in the current package or other considered name sources, the compiler cannot automatically infer that this name belongs to `com.example.catalog.api.Product`.

`requires` is not a wildcard import for a module. It does not bring all types in the module into the name scope of the source file.

## 7. Import also does not bypass exports

Even when the orders module has declared:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

orders can only use the packages that catalog allows access to under JPMS rules.

For example, catalog only exports its API:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

A class located in an internal package:

```java
package com.example.catalog.internal;

public class ProductRepositoryImpl {
}
```

The orders module cannot turn an internal package into a public API simply by writing:

```java
import com.example.catalog.internal.ProductRepositoryImpl;
```

Import does not grant additional access permissions. For external code to access a package in the normal way, the owning module must export that package and the consuming module must read the owning module. Afterward, standard Java access modifiers continue to apply.

This is why `requires`, `exports`, and `import` must be understood together:

- `requires` establishes readability between modules.
- `exports` exposes a package from the owning module.
- `import` helps source code reference types in an already accessible package.

## 8. Does import create a dependency for Maven or Gradle?

No. Import does not automatically add a library to the build configuration and does not download JARs from a repository.

Example:

```java
import org.example.json.JsonParser;
```

This import line is only valid if the `JsonParser` type is already available on the appropriate classpath or module path. If the library has not been provided, the compiler cannot find that type.

In Gradle, an artifact dependency can be declared:

```groovy
dependencies {
    implementation "org.example:json-library:1.2.0"
}
```

If the library is a named module and the current module runs under JPMS, the descriptor also needs to declare the corresponding module:

```java
module com.example.application {
    requires com.example.json;
}
```

The module name `com.example.json` must match the module name that the JAR actually declares; the artifact name and the module name do not necessarily have to be identical.

Thus there are three separate concerns:

1. The build tool supplies the artifact and dependency version.
2. `requires` declares which modules the current module needs to read.
3. `import` helps source code use type or member names.

## 9. When an application runs on the classpath

When running on the classpath, classes belong to the unnamed module of the corresponding classloader. In this model, the application does not declare dependencies with `requires` for each JAR on the classpath.

Java source code can still use `import` as usual:

```java
import java.util.List;
import com.example.catalog.api.Product;
```

When migrating to a named module on the module path, source code can still keep those imports, but the module descriptor needs to declare the corresponding readability relationships. Used packages must also be exported by the owning module under JPMS rules.

A named module cannot declare `requires` directly to the unnamed module. Therefore, when migrating a legacy application to JPMS, it is necessary to review how legacy libraries are provided and the boundary between the classpath and module path.

## 10. Common Errors and How to Understand Them

| Situation | Cause | Resolution |
|---|---|---|
| Importing a type from a named module reports package not visible | The current module does not yet read the owning module | Add `requires` with the exact module name |
| Already required, but simple class name is not found | The source file has not imported the type or used the fully qualified name | Add `import` or write the fully qualified name |
| Importing an internal package is rejected | The owning module has not exported the package | Use an exported API or redesign module boundaries |
| Import is present, but the build reports package not found | The artifact is not on the classpath/module path yet | Declare the dependency in Maven/Gradle or configure the appropriate path |
| Adding import does not change the module graph | Import does not participate in module resolution | Declare the dependency in `module-info.java` |
| Adding requires, yet code still reports short type name not found | Requires does not import type names into the compilation unit | Add the corresponding import |

When reading compilation errors, determine which level the error belongs to. Module readability errors usually relate to `requires`; package visibility errors relate to `exports`; type name errors in source code usually relate to `import`, fully qualified names, or artifact provisioning.

## 11. Checklist when using a type from another module

When you need to use a type from another module, you can check in order:

1. **Identify the artifact containing the type:** locate the exact JAR or module owning the package.
2. **Check the path:** ensure the artifact is provided on the module path for modular applications.
3. **Determine the module name:** use the actual name published by the descriptor or automatic module.
4. **Check package export:** the owning module must export the package to be used.
5. **Declare requires:** the current module must read the owning module.
6. **Import the type:** add an import in the Java file if you want to use the simple name.
7. **Compile and run:** verify both the module graph and runtime dependencies.

For example, to use `Product` from `com.example.catalog.api`, the catalog module must expose that package, the orders module must declare `requires com.example.catalog;`, the catalog artifact must be present on the module path, and the Java file can write `import com.example.catalog.api.Product;`.

## Conclusion

`requires` and `import` solve two different problems in Java. `requires` is a JPMS directive that declares which modules the current module needs to read and participates in building the module graph. `import` is a compilation unit declaration that helps source code reference types or members by short names.

Import does not create a module dependency, does not add JARs to the build, and does not bypass `exports` boundaries. Requires also does not automatically bring class names into the scope of every Java file. When a named module uses a type from another module, you must ensure the artifact is present, the module is read, the package is exported, and the source code references the type via import or a fully qualified name.

Remember the three layers of responsibility: the build tool provides the libraries, `requires` establishes module relationships, and `import` makes source code easier to write and read.