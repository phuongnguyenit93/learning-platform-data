# Strong Encapsulation of Module Packages

## Objectives

After this lesson, you will be able to:

- Explain strong encapsulation in the Java Platform Module System (JPMS).
- Distinguish between an exported package and an open package.
- Declare `exports`, qualified exports, `opens`, qualified opens, and `open module`.
- Understand the impact of module encapsulation on reflection and frameworks.
- Use `--add-exports` or `--add-opens` when compatibility is needed during development or application runtime.
- Identify package access errors and choose the appropriate way to handle them.

## 1. What Is Strong Encapsulation?

Before JPMS, Java applications typically organized classes into packages, but packages on the classpath did not create clear module boundaries. A library could contain an internal package such as `com.example.library.internal`; other code could still import the public classes in that package if the classes were on the classpath.

JPMS introduces intentional module boundaries. A named module only allows other modules to access its packages according to the permissions declared in its module descriptor. Packages that are not exported are kept hidden from code in other modules, even when the package contains public classes.

Example:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

The `com.example.customer` module exports only the `com.example.customer.api` package. The `com.example.customer.internal` package can still contain public classes, but other modules cannot use those classes as part of the regular API.

Strong encapsulation means that a module explicitly controls which packages are accessible across module boundaries and which packages are for internal use only. It helps reduce dependencies on implementation details, limits external libraries from accidentally using internal APIs, and allows module authors to change implementations with minimal impact on consumers.

This is an encapsulation mechanism at the module level, not a security sandbox for isolating malicious code. JPMS should not be treated as a protective boundary replacing application or operating system security controls.

## 2. exports: Exposing Packages to Other Modules

The `exports` directive allows other modules to access the public types in the exported package, along with the members permitted by Java's access rules:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Example API package:

~~~java
package com.example.customer.api;

public class CustomerService {

    public Customer findById(String id) {
        return new Customer(id);
    }
}
~~~

A consumer module can declare a dependency:

~~~java
module com.example.application {
    requires com.example.customer;
}
~~~

And import the public API:

~~~java
import com.example.customer.api.CustomerService;
~~~

If the `com.example.customer.internal` package is not exported, the consumer module cannot import public classes in that package in the usual way. A class having the `public` modifier does not automatically make its package public across module boundaries.

`exports` does not make private members or package-private members public. Once a package is exported, standard Java access control rules still apply.

### 2.1. Qualified exports

If a package should only be used by certain specific modules, use qualified exports:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    exports com.example.customer.spi to com.example.application,
                                      com.example.customer.adapter;
}
~~~

Here:

- `com.example.customer.api` is exported unrestrictedly to modules that read this module.
- `com.example.customer.spi` is exported only to the two listed modules.
- Other modules not in the list cannot access that SPI package across module boundaries.

Qualified exports are useful when you want to share an API among a group of collaborating modules while keeping that package outside the library's general public surface.

## 3. opens: Allowing Deep Reflection

`exports` mainly serves API access under standard Java rules. Frameworks may need reflective access to non-public constructors, fields, or methods, for example:

- Dependency injection needs to read annotations or assign private fields.
- ORM needs to read and write private fields of entities.
- JSON mappers need to invoke constructors or access non-public fields.
- Test frameworks need to inspect internal components.

The `opens` directive allows deep reflection into a package at runtime:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.persistence;
}
~~~

The `com.example.customer.persistence` package is opened for reflection from other modules. This does not mean the package is exported for other modules to import types directly in source code.

### 3.1. Qualified opens

If only one framework module needs reflection, restrict the package opening:

~~~java
module com.example.customer {
    requires org.hibernate.orm.core;

    exports com.example.customer.api;

    opens com.example.customer.persistence
            to org.hibernate.orm.core;
}
~~~

In this example, the Hibernate module is allowed deep reflection into the persistence package. Other modules do not receive that permission merely because the package has been opened to Hibernate.

Use qualified opens when you know exactly which modules need access. This expresses intent in the module descriptor and avoids opening packages more broadly than necessary.

## 4. Distinguishing exports and opens

| Capability | `exports p` | `opens p` |
|---|---|---|
| Other modules import public types in the package at compile time | Yes | No |
| Access public API under Java rules | Yes | Does not grant source-level access |
| Deep reflection into private members | No | Yes |
| Primary purpose | Expose API | Support frameworks/reflection at runtime |

Both directives can be used for the same package if the package is both an API and requires deep framework access:

~~~java
module com.example.customer {
    exports com.example.customer.model;
    opens com.example.customer.model to org.example.mapper;
}
~~~

In many designs, API packages and packages needing reflection should be separated. This helps the module descriptor clearly express what is the API for consumers and which packages are opened for frameworks.

## 5. How Is Reflection Restricted?

Suppose a module contains a model:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Model class:

~~~java
package com.example.customer.internal;

public class CustomerRecord {

    private String email;

    public CustomerRecord(String email) {
        this.email = email;
    }
}
~~~

A framework in another module wants to read the private field `email`:

~~~java
Class<?> type = record.getClass();
Field field = type.getDeclaredField("email");

boolean accessible = field.trySetAccessible();

if (accessible) {
    Object value = field.get(record);
    System.out.println(value);
} else {
    throw new IllegalStateException(
            "Package is not open to the framework module");
}
~~~

If the package containing `CustomerRecord` is not open to the framework module, `trySetAccessible()` may return `false`. Calling `setAccessible(true)` in an unpermitted situation may throw `InaccessibleObjectException`.

To allow the framework module deep access, the module owning the class can declare:

~~~java
module com.example.customer {
    exports com.example.customer.api;

    opens com.example.customer.internal
            to org.example.mapper;
}
~~~

If the framework runs in the unnamed module on the classpath, you can open the package to `ALL-UNNAMED` via a launcher option, or consider migrating the framework to a named module so access permissions are declared explicitly.

Note: `opens` does not make private fields public. It allows reflection to bypass certain Java access checks when the caller belongs to a module granted open access, subject to the conditions of the reflection API.

## 6. open module: Opening All Packages

If a module is designed primarily for frameworks that require deep reflection across many packages, you can declare an open module:

~~~java
open module com.example.customer {
    requires java.sql;
    exports com.example.customer.api;
}
~~~

`open module` makes all packages in the module open for deep reflection at runtime.

This is not equivalent to exporting all packages. Other modules still cannot import public types from unexported packages in the usual way.

With an open module, you do not declare individual `opens` directives in the module descriptor. If only a few packages require reflection, you should use specific `opens` directives rather than opening the entire module.

## 7. Granting Additional Access via the Command Line

During development, migration, or integration of legacy libraries, sometimes you cannot modify the module descriptor immediately. The JDK provides options to grant additional access at compile time or runtime.

### 7.1. --add-exports

`--add-exports` adds export access for a package to a target module:

~~~bash
javac \
    --module-path mods \
    --add-exports com.example.customer/com.example.customer.internal=com.example.application \
    -d out \
    src/com.example.application/module-info.java \
    src/com.example.application/com/example/application/Main.java
~~~

Syntax:

~~~text
--add-exports <module>/<package>=<target-module>
~~~

The example above allows `com.example.application` to access public types in the internal package of `com.example.customer` during compilation.

When running the application, if the same access is needed at runtime, pass the corresponding option to the launcher:

~~~bash
java \
    --module-path mods \
    --add-exports com.example.customer/com.example.customer.internal=com.example.application \
    -m com.example.application/com.example.application.Main
~~~

### 7.2. --add-opens

`--add-opens` opens a package for deep reflection at runtime:

~~~bash
java \
    --module-path mods \
    --add-opens com.example.customer/com.example.customer.internal=org.example.mapper \
    -m com.example.application/com.example.application.Main
~~~

Syntax:

~~~text
--add-opens <module>/<package>=<target-module>
~~~

If the framework is on the classpath, you can use:

~~~bash
java \
    -cp libs/mapper.jar \
    --add-opens com.example.customer/com.example.customer.internal=ALL-UNNAMED \
    -m com.example.application/com.example.application.Main
~~~

`--add-opens` is a runtime option; it does not make the package importable in source code during compilation. If compiled code needs access to public types in an unexported package, use `--add-exports` or update the module descriptor.

### 7.3. Comparing the Options

| Option | Phase | Effect |
|---|---|---|
| `--add-exports` | Compile time with `javac`, or runtime with `java` | Adds access to public APIs of a package |
| `--add-opens` | Runtime | Allows deep reflection into a package |
| `--add-reads` | Compile time or runtime depending on the tool | Adds a readability relationship between modules |

These options address three different aspects: package visibility, reflective access, and module readability. A module can read another module yet still lack access to unexported packages; an exported package also does not automatically open private members for deep reflection.

## 8. Observing Export and Open Status via the Java API

`java.lang.Module` provides methods to inspect module relationships:

~~~java
Module source = record.getClass().getModule();
Module caller = Mapper.class.getModule();

boolean canRead = caller.canRead(source);

boolean exported =
        source.isExported(
                "com.example.customer.internal",
                caller);

boolean open =
        source.isOpen(
                "com.example.customer.internal",
                caller);

System.out.println("Can read: " + canRead);
System.out.println("Exported: " + exported);
System.out.println("Open: " + open);
~~~

Meaning:

- `canRead(...)` checks whether the caller module has readability to the source module.
- `isExported(packageName, target)` checks whether the package is exported to the target module.
- `isOpen(packageName, target)` checks whether the package is open for deep reflection to the target module.

These APIs are useful when a framework needs to diagnose why reflection or type access failed. They also help log clearly which module is missing permissions instead of reporting only a generic reflection error.

## 9. Strong Encapsulation of JDK Internals

JPMS was introduced in Java 9, and the process of tightening access to internal JDK APIs took place across multiple releases.

Starting in Java 16, strong encapsulation was applied more broadly by default to internal JDK APIs. Java 17 completed the strong encapsulation of JDK internals under JEP 403. A few critical internal APIs still have compatibility exceptions, but applications should not rely on `sun.*` packages or unsupported implementation details.

The `--illegal-access` option previously supported a transition period for some legacy reflective accesses in earlier releases. Since JDK 17, this option no longer restores the old access mechanism; it is disabled and only emits a warning when used.

If an older library encounters access errors, the approach should be:

1. Update the library to a version that supports JPMS and the target JDK.
2. Prefer public, supported JDK APIs over internal APIs.
3. If temporary compatibility is needed, identify the exact module/package/target and use the appropriate `--add-exports` or `--add-opens`.
4. Document and remove temporary overrides once the library has been updated.

You should not open JDK packages wholesale or add broad permissions just to silence error messages. Doing so makes dependencies on implementation details harder to detect and maintain.

## 10. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `package ... is not visible` | Package is not exported to the consumer module | Declare `exports` or `--add-exports` |
| `InaccessibleObjectException` | Package is not open to the module performing reflection | Use `opens` or `--add-opens` |
| `trySetAccessible()` returns `false` | Deep access conditions are not met | Check the package, caller module, and open relationship |
| Framework can access public API but cannot read private fields | Package is only exported, not open | Add qualified `opens` for the framework |
| Code can read the module but cannot import a package | Readability exists but package visibility does not | Check `requires` and `exports` separately |
| Application depending on `sun.*` fails after JDK upgrade | Internal API has been strongly encapsulated | Switch to a supported API or update the library |

When troubleshooting errors, identify three pieces of information: the module owning the package, the package needing access, and the caller module. Only then decide whether readability, export, or open is needed. Choosing the right permission keeps the module descriptor aligned with the design rather than granting overly broad access.

## 11. Summary

JPMS strong encapsulation places packages under the control of the module descriptor. `exports` exposes a package for API access under Java rules; `opens` allows deep reflection at runtime. Qualified exports and qualified opens restrict permissions to specific modules, while `open module` opens all packages for reflection without automatically exporting them.

When encountering access errors, distinguish between readability, package export, and reflective open. Use `--add-exports` or `--add-opens` as targeted overrides when necessary, then move the required permissions into the module descriptor or update frameworks so the application maintains clear module boundaries.

References:

- [The Java Module System — JLS, Chapter 7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [AccessibleObject — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
