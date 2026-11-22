# Qualified Opens for Restricted Reflection

## Objectives

After this lesson, you will be able to:

- Explain qualified opens in the Java Platform Module System (JPMS).
- Declare a package open only to the exact module that needs reflection.
- Distinguish `opens`, `exports`, `open module`, and command-line `--add-opens`.
- Identify the exact module performing reflection inside a framework or library.
- Check open permissions at runtime and diagnose `InaccessibleObjectException`.
- Limit risk using specific packages, specific targets, and testing on the module path.

## 1. Why Are Qualified Opens Needed?

JPMS encapsulates packages inside a named module. A module does not automatically allow other modules to access all of its internal members. This is strong encapsulation: a module exposes an API by contract and keeps implementation details internal.

Some frameworks need deep reflection to do their work. For example:

- An ORM needs to read or assign private fields of an entity.
- A dependency injection framework needs to access annotated constructors or fields.
- A serializer needs to read fields to convert objects into JSON/XML.
- A framework creates proxies or reconstructs objects from data.

If the package containing those members is not opened to the module performing reflection, calling `setAccessible(true)` can fail with `InaccessibleObjectException`.

Not the entire module needs to be opened. Typically, only a few packages containing entities or metadata need to be accessed by a framework. **Qualified opens** allow opening only the specific package to one or a defined group of target modules.

## 2. Syntax of Qualified Opens in module-info.java

Syntax:

~~~java
opens <package-name> to <target-module>[, <target-module>...];
~~~

Example of a domain module having a public API and a persistence package for an ORM:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Meaning:

- `com.acme.domain` is the module owning the package.
- `com.acme.domain.persistence` is the opened package.
- `com.acme.orm` is the module permitted to perform deep reflection into that package.
- Other packages of the module remain encapsulated under normal rules, unless another directive applies.

If two frameworks genuinely need access to the same package, both targets can be declared:

~~~java
module com.acme.domain {
    opens com.acme.domain.persistence
        to com.acme.orm, com.acme.mapper;
}
~~~

Target names must be the actual module names in which the frameworks run. Do not guess a module name from the artifact name or Java package name.

### 2.1. Which Package Is Opened?

The `opens` directive applies to a specific package. If entities reside in:

~~~text
com.acme.domain.persistence
~~~

then opening that package does not automatically open other packages such as:

~~~text
com.acme.domain.internal
com.acme.domain.security
com.acme.domain.admin
~~~

If a framework needs reflection into multiple packages, list each package that actually needs it. This keeps the descriptor explicit about the permitted boundaries.

## 3. What Do Qualified Opens Allow?

Qualified opens allow the target module to perform deep reflective access into the opened package, according to the rules of the Java Reflection API.

For example, an entity has private fields:

~~~java
package com.acme.domain.persistence;

public class CustomerEntity {

    private Long id;
    private String email;

    public CustomerEntity() {
    }
}
~~~

An ORM may need to find the field and enable access:

~~~java
Field emailField =
        CustomerEntity.class.getDeclaredField("email");

if (!emailField.trySetAccessible()) {
    throw new IllegalStateException(
            "ORM cannot access CustomerEntity.email"
    );
}
~~~

If `com.acme.domain.persistence` is opened to the exact module containing this ORM code, `trySetAccessible()` can enable deep reflective access when other conditions are satisfied.

If the package is not opened to the calling module, `trySetAccessible()` can return `false`. If `setAccessible(true)` is used, the call can throw `InaccessibleObjectException`.

Qualified opens do not mean the framework has permission to modify every field in every situation. Reflection is still subject to Java's restrictions; for instance, certain final fields of records, hidden classes, or static final fields cannot be made writable merely by opening a package.

## 4. Distinguishing opens and exports

`opens` and `exports` serve two different contracts.

| Criterion | `exports` | `opens` |
|---|---|---|
| Purpose | Exposes a package's API | Allows deep reflection |
| Normal source code access | Allows modules to read public API if they have readability | Grants no import/normal API access permission |
| Reflection on private members | Not automatically permitted | Allows target modules to perform deep reflection |
| Scope | Public types/members under Java rules | Package opened for reflection |
| Primary phase | Compile time and runtime | Runtime |

Example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Consumer modules can import public APIs in `com.acme.domain.api` if they have an appropriate readability relationship. The ORM can perform deep reflection into `com.acme.domain.persistence`. The two packages serve two separate purposes.

A qualified opens does not turn a package into a public API. If other code needs to import classes in that package, design an appropriate API or export instead of using opens to work around compile errors.

## 5. Distinguishing Qualified Opens, Unqualified Opens, and Open Modules

### 5.1. Unqualified Opens

~~~java
module com.acme.domain {
    opens com.acme.domain.persistence;
}
~~~

This directive opens the package to every module at runtime. It is broader than qualified opens because it does not restrict the target module.

Use it only when the design truly requires any module to be able to perform deep reflection into that package. For specific frameworks, prefer qualified opens.

### 5.2. Open Module

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
    requires com.acme.common;
}
~~~

Declaring `open module` opens all packages of the module for deep reflection at runtime. This is a very broad scope.

An open module cannot declare additional individual `opens` directives inside its descriptor. If you need to open a few packages in a controlled manner, use a normal module with qualified opens.

### 5.3. Selection Table

| Declaration | Scope |
|---|---|
| `opens p to m;` | Only module m |
| `opens p;` | All modules |
| `open module M { ... }` | All packages of module M |

For an ORM that needs to access private entity fields, `opens package to orm.module` is usually the choice that expresses the intent most accurately.

## 6. Identifying the Correct Target Module of the Framework

A common configuration mistake is opening the package to the application module while the code actually performing reflection lives inside the framework module.

Example call flow:

~~~text
Application module
       |
       | calls API
       v
ORM framework module
       |
       | Field.setAccessible(...)
       v
Domain module
  package persistence
~~~

The module that needs to be put in the target of qualified opens is the module performing the reflection operation, which in this example is `com.acme.orm`. The application module that merely calls the ORM API is not necessarily the module that needs that permission.

### 6.1. Checking a JAR's Module Name

You can use the command:

~~~bash
jar --describe-module --file libs/acme-orm.jar
~~~

This command displays the module descriptor or automatic module name of the JAR. If the JAR declares `Automatic-Module-Name` in its manifest, that name is normally used as the module name when running on the module path.

Do not assume a Maven artifact name or package name is the module name without verifying.

You can check which modules the JVM recognizes with:

~~~bash
java --list-modules
~~~

In a running application, you can log the module of the class performing reflection:

~~~java
Module frameworkModule = OrmInternalAccessor.class.getModule();

System.out.println(frameworkModule.getName());
~~~

If `getName()` returns `null`, the class belongs to the unnamed module. That case requires different handling from qualified opens in the descriptor.

## 7. When the Framework Runs on the Classpath

Qualified opens in `module-info.java` specify targets by module name. They cannot declare the special target `ALL-UNNAMED`.

If the framework still runs in the unnamed module on the classpath, a temporary command-line option can be used:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.persistence=ALL-UNNAMED -cp app.jar:libs/* com.acme.Main
~~~

This flag opens the package at runtime to unnamed modules. It is useful for confirming a diagnosis or supporting a library that cannot yet be moved to a named module.

If the framework is already a named module, open the package to that exact module:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.persistence=com.acme.orm --module-path mods -m com.acme.app/com.acme.Main
~~~

`--add-opens` is an external runtime configuration. It does not change the source descriptor packaged inside the module and is not a compile-time directive for `javac`.

In the long run, consider moving the framework to the module path if the library supports it, then record qualified opens in the descriptor of the module owning the package. That way, reflection permissions become part of the module contract that can be reviewed and versioned alongside source code.

## 8. Checking Openness at Runtime

Java provides an API to query whether a module opens a package to another module.

~~~java
Module domainModule = CustomerEntity.class.getModule();
Module ormModule = OrmInternalAccessor.class.getModule();

boolean openToOrm = domainModule.isOpen(
        "com.acme.domain.persistence",
        ormModule
);

System.out.println("Persistence package open to ORM: " + openToOrm);
~~~

`Module.isOpen(packageName, otherModule)` checks whether the package is open to the specified target module. It helps confirm that the runtime sees the openness relationship as expected.

You can combine this check with `trySetAccessible()` on the actual member that needs to be accessed:

~~~java
Field field = CustomerEntity.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package is not open to the framework module"
    );
}
~~~

These two checks serve different purposes:

- `isOpen` confirms the module configuration.
- `trySetAccessible` confirms whether the specific member can have reflective access enabled in the current context.

Do not test solely with a run on the classpath. When all code resides in the unnamed module, module boundaries can differ from production. Run integration tests on the module path matching the deployment environment.

## 9. Risks of Opening Packages Too Broadly

### 9.1. Exposing Implementation Details

When a package is opened to a framework, the framework can depend on private fields, member names, or object layouts. An internal refactor can break the application even though the public API has not changed.

### 9.2. Increasing Coupling to the Framework

Qualified opens create an operational dependency between the domain module and the framework. When switching ORMs or serializers, the target module name and package list may need to change.

### 9.3. Opening to the Wrong Module

If opened to the application module while the framework performs reflection, the configuration still will not resolve the error. If opened to `ALL-UNNAMED`, many libraries on the classpath may receive broader permissions than intended.

### 9.4. Tests Not Reflecting Production

Tests run on the classpath may fail to reproduce named-module encapsulation errors. Conversely, a test JVM with global `--add-opens` flags can mask a descriptor missing qualified opens.

### 9.5. Upgrade Difficulties

A framework may change its module name, change how it performs reflection, or no longer need the old package. An outdated descriptor might retain unnecessary permissions, or cause module resolution to fail if the target module is no longer present in the runtime configuration.

## 10. Process for Designing Restricted Qualified Opens

### Step 1: Identify Members and Packages That Actually Need Reflection

Record the class, package, and reflection operation causing the error. Do not open the entire domain module just because one entity field is blocked.

### Step 2: Identify the Module Performing Reflection

Retrieve the module from the class invoking `setAccessible` or `trySetAccessible`. Verify the framework's module name via its JAR descriptor or runtime inspection.

### Step 3: Declare Qualified Opens

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

Add only the packages and targets with a confirmed need.

### Step 4: Run Integration Tests on the Module Path

Verify that:

- The domain module resolves successfully.
- The framework is loaded under the expected target module.
- Reflection on the required members works.
- Unrelated packages remain closed.
- Serialization, entity hydration, or injection flows work as expected.

### Step 5: Document the Contract and Review Timing

In the module documentation or architectural configuration, record:

- Why the package must be opened.
- Which framework/target module receives the permission.
- Which component owns the directive.
- The tested framework version.
- Conditions for narrowing or removing the directive when the framework changes.

## 11. Complete Example

Suppose the project has two modules:

~~~text
modules/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/
│       ├── api/
│       │   └── CustomerService.java
│       └── persistence/
│           └── CustomerEntity.java
└── com.acme.orm/
    ├── module-info.java
    └── com/acme/orm/
        └── OrmInternalAccessor.java
~~~

Domain descriptor:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.persistence to com.acme.orm;
}
~~~

ORM descriptor:

~~~java
module com.acme.orm {
    requires com.acme.domain;
}
~~~

In the example, the ORM can use the domain's exported public API and perform deep reflection into the opened persistence package. It is not automatically permitted to perform deep reflection into other packages of the domain.

At runtime, both modules must be present on the module path and the module name must match the qualified opens:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

If the target module `com.acme.orm` is absent from the runtime configuration or the name in the descriptor does not match the actual module name, the configuration cannot fulfill its design intent.

## 12. Review Checklist

Before adding or keeping a qualified opens, confirm:

- [ ] The specific package containing members needing reflection has been identified.
- [ ] The exact module performing reflection has been identified.
- [ ] The target in the directive matches the actual module name.
- [ ] Only necessary packages are opened; `open module` is not used for a narrow need.
- [ ] `exports` is not used in place of `opens` when deep reflection is needed.
- [ ] `Module.isOpen` or `trySetAccessible` behavior has been verified at runtime.
- [ ] Integration tests run on a module path similar to production.
- [ ] The rationale, framework version, and directive owner have been documented.
- [ ] A plan exists to review upon framework upgrades or package changes.

## Conclusion

Qualified opens are an explicit declaration that a package needs to support deep reflection for a specific module. They keep the remaining packages encapsulated and help the module descriptor accurately reflect integration needs with ORMs, serializers, or dependency injection frameworks.

Start from the members and packages needing access, find the exact module performing reflection, and then open the package to that target. **Opening the right package to the right module and testing on the module path** preserves the benefits of strong encapsulation while still supporting frameworks that require reflection.
