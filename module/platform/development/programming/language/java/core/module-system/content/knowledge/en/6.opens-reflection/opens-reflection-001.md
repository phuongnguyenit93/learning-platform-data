# opens package for runtime deep reflection

In the Java Platform Module System (JPMS), a package can be opened so that other modules can use reflection to deeply access non-public members. The `opens` directive in `module-info.java` grants this permission at runtime. It is especially important for ORMs, dependency injection, JSON serializers, binding frameworks, and libraries that need to read or set private fields, invoke non-public constructors, or inspect annotations on implementations.

`opens` does not expose a package for ordinary Java code to import and call public types in that package. Language-level API access is still governed by `exports` and access modifiers. Therefore, you need to choose the right directive according to the type of access the framework requires.

## 1. Regular reflection and deep reflection

Reflection allows a program to inspect classes, methods, constructors, fields, and annotations at runtime. For example:

```java
Class<?> type = Customer.class;

for (var field : type.getDeclaredFields()) {
    System.out.println(field.getName());
}
```

APIs such as `getDeclaredFields()` can list even private fields. However, seeing a member's metadata does not mean being permitted to read or modify its value. Java still enforces access checks when reflection performs operations on the member.

Deep reflection is the ability to bypass normal access restrictions to operate on members such as `private` or package-private ones. On Java with the module system, a module containing a package must be opened to the module performing deep reflection. If the package is not opened appropriately, attempting to bypass access checks can fail with `InaccessibleObjectException`.

For example, an ORM may need to read private fields to map database columns, or invoke a non-public constructor when reconstructing an entity. This is the use case `opens` is designed to support.

## 2. Declaring opens in module-info.java

There are two common declaration forms.

### Opening a package to all modules

```java
module com.acme.domain {
    opens com.acme.domain.entity;
}
```

The package `com.acme.domain.entity` is opened to all modules for deep reflection at runtime. This is convenient when many different frameworks or modules need to reflect into that package, but the permission scope is broader than necessary.

### Opening a package only to specified modules

```java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
```

This is qualified opens. Only the module `com.acme.orm` is permitted to perform deep reflection into the package `com.acme.domain.entity`. Other modules still do not have that permission merely because they read `com.acme.domain`.

Multiple target modules can be specified:

```java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm, com.acme.json;
}
```

The target module name must match the name in the framework's module descriptor. Using qualified opens helps restrict reflection permissions to the exact components that need them.

## 3. How does opens differ from exports?

The two directives address two different needs:

| Directive | Purpose | Ordinary Java code access | Deep reflection |
|---|---|---|---|
| `exports p` | Exposes the package as an API for other modules | Can access public types in the package if the module reads it and access modifiers allow | Does not automatically grant deep access to private members |
| `opens p` | Opens the package for reflection at runtime | Does not allow other modules to import and call the package's API in the usual way | Allows deep reflection |
| `exports p to m` | Exposes the API only to the target module | Only the listed module | Does not automatically open private members |
| `opens p to m` | Opens reflection only to the target module | Does not expose the API at compile time | Allows the target module to perform deep reflection |

If a package is both a public API and needs a framework to access private fields, both can be combined:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
```

In this example, the application uses the public types in the API package; the ORM is granted reflection access to the entity package. You should not add `opens` just because another module needs to call a public method, nor should you add only `exports` when a framework needs to operate on private fields.

## 4. Example: opening an entity for an ORM

Suppose the domain module contains an entity with a private field:

```java
// module-info.java of com.acme.domain
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
```

Entity:

```java
package com.acme.domain.entity;

public class Customer {
    private String email;

    public Customer(String email) {
        this.email = email;
    }
}
```

The ORM module declares a dependency if it needs to read the domain module:

```java
module com.acme.orm {
    requires com.acme.domain;
}
```

When the ORM receives a `Customer` object from the application or from an entity creation mechanism, it can access the field using reflection:

```java
import java.lang.reflect.Field;

public class EntityInspector {
    public static Object readEmail(Object entity)
            throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField("email");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Module does not open the entity package to this ORM"
            );
        }

        return field.get(entity);
    }
}
```

When the code above runs from the `com.acme.orm` module, the package `com.acme.domain.entity` is opened to that module, so `trySetAccessible()` can succeed. If the `opens` directive is omitted, the JVM can refuse bypassing access checks, even though reflection still finds the field named `email`.

This example focuses on reflection operations on an already-provided object. If the ORM needs to directly reference the `Customer` type in source code, the package containing that type must also be exported appropriately. `opens` does not replace that requirement.

## 5. Related reflection APIs

Classes in `java.lang.reflect` provide commonly used APIs when doing deep reflection:

- `AccessibleObject.trySetAccessible()`: attempts to enable access bypassing Java language checks; returns `true` if successful and `false` if it cannot be enabled.
- `AccessibleObject.setAccessible(true)`: requests enabling access; may throw `InaccessibleObjectException` when the module system does not allow it.
- `AccessibleObject.canAccess(target)`: checks whether the member can currently be accessed with a specific receiver.
- `Field.get(target)` and `Field.set(target, value)`: read or write a field after appropriate access has been set.
- `Method.invoke(target, args...)`: invokes a method using reflection.
- `Constructor.newInstance(args...)`: creates an object using a constructor found via reflection.

Example of handling the case where the package is not opened:

```java
Field field = entity.getClass().getDeclaredField("email");

if (field.trySetAccessible()) {
    Object value = field.get(entity);
    System.out.println(value);
} else {
    System.out.println("The package is not open to this module");
}
```

Prefer `trySetAccessible()` when the application needs to handle the unopened-package case in a controlled manner. If using `setAccessible(true)`, be prepared to handle `InaccessibleObjectException`. Do not call `setAccessible(true)` mechanically on every member; only enable access for members that actually need to be operated on.

## 6. Opening an entire module with open module

If a module declares:

```java
open module com.acme.domain {
    requires java.sql;
}
```

then all packages of the module are opened for deep reflection from any module at runtime. This is a broader option than individual `opens` directives.

An open module does not need to declare each package with `opens`; opening applies to all packages of the module. You should not use `open module` just to solve a single framework needing access to one package, because doing so widens the reflection scope for all packages.

For applications with strict encapsulation requirements, prefer `opens package to framework.module;` to grant permission only to the specific package and framework. Use an open module when the design genuinely requires all packages to be reflectable by multiple modules.

## 7. Opening a package with the JVM option --add-opens

When you cannot modify a library's `module-info.java`, you can open a package at JVM startup using `--add-opens`.

Syntax:

```shell
java --add-opens source.module/package=target.module ...
```

Example of opening an application module's package for an ORM:

```shell
java --add-opens com.acme.domain/com.acme.domain.entity=com.acme.orm \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

If the framework runs on the classpath and belongs to the unnamed module, you can use `ALL-UNNAMED`:

```shell
java --add-opens com.acme.domain/com.acme.domain.entity=ALL-UNNAMED \
     -jar application.jar
```

`--add-opens` only adds package-opening permission for the runtime of that run. It does not modify the JAR file, does not change `module-info.java` in the artifact, and does not automatically create compile-time access. For build configurations or deployment environments, this argument must be placed in the actual JVM command used.

Do not confuse the two options:

- `--add-opens` grants deep reflection permission at runtime.
- `--add-exports` allows access to public types of a package across module boundaries; it does not open private members for deep reflection.

## 8. Checking whether a package is already opened

You can check the module and package open status directly in Java:

```java
Module sourceModule = Customer.class.getModule();
Module callerModule = EntityInspector.class.getModule();

boolean opened = sourceModule.isOpen(
    "com.acme.domain.entity",
    callerModule
);

System.out.println("Package opened: " + opened);
```

The method `Module.isOpen(packageName, otherModule)` checks whether the package is open to the target module. The method `Module.isExported(packageName, otherModule)` checks export permission for normal API access. These two checks help distinguish errors caused by missing exports from errors caused by missing opens.

When you need to inspect a JAR's descriptor:

```shell
jar --describe-module --file domain.jar
```

The descriptor information shows which packages are exported or opened and which target modules are declared in qualified opens. When inspecting a running application, also check the exact JAR and the exact JVM command used in that environment.

## 9. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `InaccessibleObjectException` when calling `setAccessible(true)` | The package of the module containing the class is not open to the calling module | Add an appropriate qualified `opens` or `--add-opens` |
| `trySetAccessible()` returns `false` | The module system does not allow bypassing access checks | Check the caller module and `opens` directives |
| Framework sees the field but cannot read its value | Metadata lookup succeeded, but deep reflection permission was not granted | Open the package to the right framework module |
| Application code cannot import a class in a package that only has `opens` | `opens` does not expose the API at compile time | Add `exports` if a public API is truly needed |
| IDE run configuration differs from the deployment environment | The `--add-opens` option was only configured in one JVM command | Synchronize VM options in the actual runtime environment |

When troubleshooting errors, identify the module performing the reflection. That module may be a framework module, an automatic module, or the unnamed module. Opening a package to the main application module may not be enough if the actual reflection operation is performed by a different framework module.

## 10. Principles for using opens safely

- Only open packages for which a framework or library genuinely needs deep reflection.
- Prefer qualified opens to limit target modules.
- Keep API packages separate from entity/implementation packages when the architecture allows.
- Only use `open module` when every package needs broad reflection access.
- Use `--add-opens` as an intentional runtime configuration when you cannot yet modify the module descriptor; document it in the deployment configuration.
- Do not confuse reflection permission with permission to call public APIs; use `exports` for APIs and `opens` for deep reflection.
- Verify the exact caller module when a framework reports an error, because permission granted to one module does not automatically apply to another module.

`opens` is the mechanism that allows frameworks to interact with internal module implementations without turning every field or method into a public API. Opening the right package to the right module enables frameworks to work in a JPMS environment while still preserving the application's access boundaries.