# Qualified opens to specific modules

In the Java Platform Module System (JPMS), a module can keep a package closed against deep reflection, and then open only the necessary package to a specified set of modules. This declaration is called **qualified opens**: using the `opens` directive followed by a list of target modules after the `to` keyword.

Qualified opens is useful when a framework needs to read or modify non-public members via reflection, while the application still wants to restrict that access to that exact framework. For example, a domain module can open its model package to a persistence module so an ORM can map entities, while other modules are not granted the same deep reflection permission.

## 1. Why is qualified opens needed?

JPMS adds access boundaries at the module level. When a package is not opened, other modules cannot by default use deep reflection to access members such as private fields, private methods, or non-public constructors.

Some frameworks need this capability to do their work without requiring developers to write manual accessor code:

- ORMs need to read entity fields, constructors, or metadata.
- Dependency injection frameworks need to inspect annotations and instantiate objects.
- Serialization libraries need to read or write object state.
- Binding frameworks need to map external data onto object properties.

If the entire module is opened for reflection, the access scope is broader than what a specific framework needs. Qualified opens lets a module specify which package is opened and which modules receive permission.

## 2. Qualified opens syntax

General syntax:

```java
module module.name {
    opens package.name to target.module.one, target.module.two;
}
```

Where:

- `opens` is the directive that opens a package for deep reflection.
- `package.name` is a package belonging to the declaring module.
- `to` begins the list of target modules granted permission.
- The names after `to` are module names, separated by commas.

Example:

```java
module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence,
           com.example.json;
}
```

The package `com.example.customer.model` is opened to the two modules `com.example.persistence` and `com.example.json`. Other modules not listed will not be granted deep reflection permission through this directive.

Qualified opens applies only to the explicitly named package. If a module has multiple packages that need to be opened to the same framework, each package requires its own directive:

```java
module com.example.customer {
    opens com.example.customer.entity
        to com.example.persistence;

    opens com.example.customer.value
        to com.example.persistence;
}
```

There is no wildcard to open all subpackages matching a prefix. Each package is a unit that must be considered and declared.

## 3. Example: opening an entity package to an ORM module

Suppose an application has two modules:

```text
customer/
└── src/
    └── com.example.customer/
        ├── module-info.java
        └── com/example/customer/
            ├── api/
            │   └── Customer.java
            └── model/
                └── CustomerEntity.java

persistence/
└── src/
    └── com.example.persistence/
        ├── module-info.java
        └── com/example/persistence/
            └── EntityMapper.java
```

The customer module has a public API and an internal entity:

```java
package com.example.customer.api;

public interface Customer {
    String id();
    String email();
}
```

The entity can encapsulate state using private fields:

```java
package com.example.customer.model;

public class CustomerEntity {
    private String id;
    private String email;

    protected CustomerEntity() {
    }

    public CustomerEntity(String id, String email) {
        this.id = id;
        this.email = email;
    }
}
```

Descriptor of the customer module:

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.model
        to com.example.persistence;
}
```

The two directives have separate purposes:

- `exports com.example.customer.api` exposes the API for ordinary Java access from other modules.
- `opens com.example.customer.model to com.example.persistence` grants deep reflection permission on the model package to the persistence module.

The persistence module descriptor declares a dependency on customer:

```java
module com.example.persistence {
    requires com.example.customer;
}
```

The persistence module can reference the exported API. Frameworks in this module can also use deep reflection on the model package because the customer module opened that package to the exact target module.

## 4. What does qualified opens allow?

When a package is opened to a target module, reflection code running in the target module can deeply access members of classes in that package, within the bounds of Java's reflection rules.

For example, the persistence module receives an entity object through an API or an internal processing flow. It can use reflection to read a private field:

```java
package com.example.persistence;

import java.lang.reflect.Field;

public class EntityMapper {
    public Object readEmail(Object entity) throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField("email");

        if (!field.trySetAccessible()) {
            throw new IllegalAccessException(
                    "The entity package is not open to this module"
            );
        }

        return field.get(entity);
    }
}
```

`trySetAccessible()` attempts to allow reflective access to the member. If the module containing the entity class has opened the package to the persistence module, the operation can be permitted according to JPMS rules. If the package is not opened appropriately, the method can return `false`; subsequent reflective operations will lack the required access permission.

In real code, frameworks usually handle accessibility checks themselves and produce error messages. The example above only illustrates where qualified opens takes effect: reflection permission is granted per module containing the reflection-calling code.

Qualified opens does not make private fields public. It does not change access modifiers in bytecode, nor does it turn the package into an ordinary Java API. It grants permission for deep reflection mechanisms within the specified scope.

## 5. Which module is the target module?

The name after the `to` keyword must be the name of the module to which the code performing reflection belongs. This is an important point when integrating frameworks.

For example, if an ORM library is packaged as the module `com.example.persistence`, the descriptor must open the package to that exact name:

```java
opens com.example.customer.model
    to com.example.persistence;
```

The module name does not necessarily match the Maven artifact name, JAR file name, or Java package name. When using third-party libraries, you need to determine the actual module name from the JAR's descriptor or from the automatic module name the JAR exposes.

You can inspect a JAR's module name with:

```shell
jar --describe-module --file libs/persistence.jar
```

If the JAR is an explicit module, the output shows the module name in its descriptor. If it is an automatic module, the tool shows the recognized module name. Use that exact name in qualified opens.

If a framework is split into multiple modules, you need to determine which module actually performs deep reflection. Do not assume that the overall artifact's module name is also the module name performing the access. You may need to check the framework documentation or the module descriptor of each component.

## 6. How does qualified opens differ from exports?

These are two directives that are easily confused because both mention a package, yet they grant different capabilities.

| Criterion | `exports` | Qualified `opens` |
|---|---|---|
| Purpose | Expose ordinary Java API | Allow deep reflection |
| Syntax | `exports package.name;` | `opens package.name to module.name;` |
| Scope | Any module reading the owning module, unless using qualified exports | Only modules listed after `to` |
| Public type access | Accessible if other Java rules allow | Does not automatically expose the package for normal source code access |
| Private access via reflection | Does not automatically grant deep reflection permission | Grants deep reflection permission within the open scope |
| Primary effect time | Compile time and runtime | Reflection at runtime |

Example of exports only:

```java
module com.example.customer {
    exports com.example.customer.api;
}
```

Other modules can compile code referencing public types in the API package. However, if a framework needs deep reflection into private fields of the model package, exporting the API package does not help for the model package.

Example of qualified opens only:

```java
module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence;
}
```

The persistence module can use deep reflection in the model package, but that does not allow it to import classes in the model package as an ordinary Java API. To allow normal source code access, an appropriate `exports` is needed.

A module can use both directives for the same package if it genuinely needs both public API access and deep reflection:

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.model
        to com.example.persistence;
}
```

## 7. Qualified opens vs. qualified exports

Qualified exports and qualified opens both have a list of target modules, but their meanings are not the same.

Qualified exports:

```java
exports com.example.customer.integration
    to com.example.orders, com.example.reporting;
```

It allows the orders and reporting modules to access the ordinary Java API in the integration package.

Qualified opens:

```java
opens com.example.customer.model
    to com.example.persistence;
```

It allows the persistence module to perform deep reflection on the model package.

Choose the directive based on the type of access to grant:

- If another module needs to call methods or reference public types in a package, consider `exports`.
- If a framework needs to access non-public fields, constructors, or methods via reflection, consider `opens`.
- If only certain modules need that capability, use the qualified form to limit the recipients.

There is no need to open a package for reflection simply because another module uses that package's public API.

## 8. Limitations and rules when declaring qualified opens

### 8.1. Only opens packages belonging to the current module

The directive must point to a package declared in the module containing the descriptor. You cannot use `opens` to open a package belonging to another module.

### 8.2. Does not automatically open subpackages

If declared:

```java
opens com.example.customer.model
    to com.example.persistence;
```

then the package `com.example.customer.model` is opened. Subpackages such as `com.example.customer.model.internal` are separate packages and are not automatically opened by prefix.

If a framework needs deep reflection in a subpackage, an additional directive must be declared for that package.

### 8.3. Qualified opens is not a compile-time API

Source code in the target module cannot rely on qualified opens to import classes belonging to an unexported package. Open is only related to deep reflection at runtime.

If both capabilities are needed, declare `exports` and `opens` separately according to their intended purpose.

### 8.4. Do not declare individual opens inside an open module

If a module begins with `open module`, all packages are already opened for deep reflection. In that case, do not declare additional individual `opens` directives inside the module body.

The following example is invalid in module syntax design:

```java
open module com.example.customer {
    opens com.example.customer.model
        to com.example.persistence;
}
```

With an open module, opening already applies module-wide. If you want to restrict permissions to specific packages and modules, use a regular `module` with qualified opens.

### 8.5. Target modules must be identified accurately

The module name after `to` is the module identity of the reflection recipient. This name needs to match the module the framework actually uses at runtime.

When a library changes its packaging or splits modules, recheck the descriptor and update qualified opens if the target module name changes.

## 9. Example configuration for multiple frameworks

Suppose an application uses an ORM module and a JSON mapper module. Both frameworks need to read entity state, but the application wants to grant reflection permission only to those two modules.

```java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.entity
        to com.example.persistence,
           com.example.json;
}
```

Here:

- The `api` package is exposed to modules reading customer.
- The `entity` package is opened to the persistence and json modules.
- Another module that reads customer but is not in the `to` list is not granted deep reflection permission via this directive.
- Other packages of customer remain closed if there is no opens directive or open module.

If a framework only needs access to the entity package, there is no need to open the entire api package or the entire module. If the framework needs an additional package, add that exact package after identifying the actual requirement.

## 10. When the framework runs on the classpath

Qualified opens lists the names of target named modules. If framework code runs in the unnamed module because it is placed on the classpath, you cannot treat its artifact name or package name as an unnamed module name to put in the `to` list.

In some legacy integration scenarios, a runtime option such as `--add-opens` targeting `ALL-UNNAMED` may be needed to open a package to code running in the unnamed module:

```shell
java --add-opens com.example.customer/com.example.customer.entity=ALL-UNNAMED ...
```

This is a JVM command-line option whose scope applies to that run. It does not replace a descriptor designed for a target named module. When the framework is moved to a named module, you should determine the actual module name and consider declaring the corresponding qualified opens in the descriptor.

Do not add broad `--add-opens` flags just to hide configuration errors. Limit the package and access target to the framework's actual needs.

## 11. How to check and troubleshoot reflection errors

When a framework reports a reflective access error, you can check step by step:

1. Identify the package containing the class the framework is operating on.
2. Identify the module that owns that class.
3. Identify the module containing the framework's reflection code.
4. Check whether the owning module's descriptor has qualified opens to the exact target module.
5. Check whether the package was confused with a subpackage or a same-named package in another module.
6. Confirm the application is running with the right artifacts and module path.
7. Rerun to verify the reflection error is resolved.

You can use `jar --describe-module` to view a JAR's module name and directives:

```shell
jar --describe-module --file libs/customer.jar
jar --describe-module --file libs/persistence.jar
```

If the descriptor does not yet open the right package, add qualified opens in the module owning the package. If the target module name is incorrect, fix the `to` list according to the framework's actual module.

## 12. Principles for designing qualified opens

When designing reflection permissions, keep these principles in mind:

- Open only the necessary packages, rather than opening an entire namespace by intuition.
- List the exact modules performing reflection.
- Keep ordinary Java APIs in intentionally exported packages.
- Only use `opens` when a framework genuinely needs deep reflection.
- Prefer qualified opens when the target module is known.
- Recheck module names when upgrading or changing framework packaging.
- Document the reason for opening a package so maintainers understand the runtime dependency.
- Re-evaluate the directive when a framework no longer needs to access that package.

Qualified opens is part of the runtime contract between the module owning the data and the framework module. When declared intentionally, a module can support ORMs, serialization, or dependency injection while still keeping reflection permissions within the necessary scope.

## Conclusion

Qualified opens is the `opens package.name to target.module;` directive in `module-info.java`. It opens a package for deep reflection from the listed modules, helping frameworks access non-public members when mapping, injecting, or serializing objects.

It differs from `exports`: exports exposes an ordinary Java API, while qualified opens grants deep reflection permission at runtime. Qualified opens also does not automatically create a module dependency and does not allow source code to import unexported packages.

When integrating a framework, accurately identify the package that needs to be opened and the module name performing reflection. Limiting the target module list helps preserve encapsulation while providing sufficient access for the runtime components that truly need it.