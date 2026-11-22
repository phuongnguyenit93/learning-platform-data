# Named Modules and Package Uniqueness

In the Java Platform Module System (JPMS), a named module owns a set of packages. When multiple named modules are resolved together in a module configuration, the package uniqueness rule clearly determines which module a package belongs to. Therefore, sharing the same package across multiple named modules (split package) is a source of conflicts during module compilation or resolution.

This rule differs from traditional JAR organization on the classpath, where multiple JARs can contribute classes to the same package in the unnamed module. When migrating an application to the module path, package structure needs to be redesigned so that each package has one clear owner.

## 1. Modules and packages are two different levels of organization

A **package** groups related Java types, for example:

    com.example.billing.api
    com.example.billing.internal

A **module** groups multiple packages into a unit with a name, dependencies, and access boundaries declared in `module-info.java`.

Example:

    module com.example.billing {
        requires com.example.shared;
        exports com.example.billing.api;
    }

Module `com.example.billing` can own multiple packages. The `exports` directive specifies which packages other modules can access under normal Java rules; it does not create packages and does not transfer package ownership to another module.

Module names and package names belong to two separate namespaces. A module can be named `com.example.billing`, while packages inside it are named `com.example.billing.api` or `com.example.billing.internal`.

## 2. Package uniqueness in named modules

Within the same module configuration, a package has only one owner, which is a single named module. Classes belonging to the same package cannot be split between two named modules resolved together in that configuration.

For example, module A has:

    package com.example.shared.util;

    public final class MoneyFormatter {
    }

While module B also has:

    package com.example.shared.util;

    public final class DateFormatter {
    }

Even though the two modules do not contain classes with the same name, they both declare the `com.example.shared.util` package. This is a **split package**: a single package scattered across multiple modules.

JPMS requires a package to have one clear owner in a module configuration. Therefore, putting both named modules containing this package into the same configuration may be rejected during compilation or module resolution.

Important point: a split package is not limited to two JARs containing a class with the same fully qualified name. Simply having two modules contain different classes while declaring the same package already creates a package conflict.

## 3. Example of a split package structure

Suppose there are two modules:

    src/
    ├── com.example.billing/
    │   ├── module-info.java
    │   └── com/example/shared/util/MoneyFormatter.java
    └── com.example.reporting/
        ├── module-info.java
        └── com/example/shared/util/DateFormatter.java

The billing module:

    module com.example.billing {
        exports com.example.shared.util;
    }

`MoneyFormatter.java` file:

    package com.example.shared.util;

    public final class MoneyFormatter {
        public static String format(long amount) {
            return amount + " VND";
        }
    }

The reporting module:

    module com.example.reporting {
        exports com.example.shared.util;
    }

`DateFormatter.java` file:

    package com.example.shared.util;

    public final class DateFormatter {
        public static String format(int year) {
            return "Year " + year;
        }
    }

Both modules declare and export `com.example.shared.util`. When compiled or resolved together, the module system cannot treat that package as belonging to both modules.

You can try compiling from the directory containing `src`:

    javac --module-source-path src -d out
        -m com.example.billing,com.example.reporting

The compiler will report an error about the package already existing in another module or the package being split across modules. The exact message may vary depending on the JDK version and how the module source path is structured.

Renaming the modules does not solve the problem. Both modules still own the same package name `com.example.shared.util`.

## 4. Fix: move the shared package into one module

If `MoneyFormatter` and `DateFormatter` truly belong to the same group of shared utilities, create a separate module that owns that package.

Structure after fixing:

    src/
    ├── com.example.shared/
    │   ├── module-info.java
    │   └── com/example/shared/util/
    │       ├── MoneyFormatter.java
    │       └── DateFormatter.java
    ├── com.example.billing/
    │   └── module-info.java
    └── com.example.reporting/
        └── module-info.java

The shared module:

    module com.example.shared {
        exports com.example.shared.util;
    }

The billing module:

    module com.example.billing {
        requires com.example.shared;
    }

The reporting module:

    module com.example.reporting {
        requires com.example.shared;
    }

Now the `com.example.shared.util` package belongs solely to the `com.example.shared` module. Both billing and reporting modules read the shared module to use the exported public types.

Compile:

    javac --module-source-path src -d out
        -m com.example.shared,com.example.billing,com.example.reporting

This approach clearly expresses ownership: the shared module is responsible for the utility types, while the billing and reporting modules are simply consuming modules.

## 5. Alternative fix: split packages by responsibility

Not every class with a colliding package is truly a shared component. If they belong to different business domains, you can place them into separate packages:

    com.example.billing.internal
    com.example.reporting.internal

For example, the billing module owns:

    package com.example.billing.internal;

    public final class MoneyFormatter {
    }

The reporting module owns:

    package com.example.reporting.internal;

    public final class DateFormatter {
    }

These two packages are distinct, so they can belong to two different named modules in the same configuration.

Separating packages usually fits when classes only serve internally within one module. Do not create a shared module just to lump together classes that have no shared responsibility or no need to be shared.

## 6. A subpackage is not the same package

Package names in Java are hierarchical by naming convention, yet each full name still represents a distinct package.

Example:

- `com.example.billing`
- `com.example.billing.api`
- `com.example.billing.internal`

These are three separate packages. Therefore, `com.example.billing` can belong to one module while `com.example.billing.api` belongs to another module, if the structure is designed that way and there are no duplicate package names.

Similarly, exporting a package does not automatically export its subpackages:

    module com.example.billing {
        exports com.example.billing;
    }

The directive above does not export `com.example.billing.api`. If you want other modules to access public types in that subpackage, declare it separately:

    module com.example.billing {
        exports com.example.billing;
        exports com.example.billing.api;
    }

The package uniqueness rule evaluates the full package name. Having two packages share a prefix does not automatically create a split package.

## 7. Relationship between package uniqueness and exports

`exports` and package ownership solve two different questions:

- **Package ownership:** which named module in the configuration does the package belong to?
- **Exports:** does the owning module allow other modules to access public types in that package?

Example:

    module com.example.internal {
        // package com.example.internal.impl exists in the module
    }

A package can belong to a module even if it is not exported. Other modules cannot import types in an unexported package, but that does not strip the module of package ownership.

Conversely, two modules exporting the same package cannot both own that package in a single module configuration. Adding `exports`, `opens`, or `requires transitive` is not a way to fix a split package; you must fix the package structure and owning module.

## 8. How do the classpath and module path differ?

Before JPMS, applications often placed many JARs on the classpath. Classes on the classpath were grouped into the unnamed module of the corresponding class loader. Thus, multiple JARs could contribute different classes to the same package.

Example:

    legacy-a.jar
      com.example.shared.util.MoneyFormatter

    legacy-b.jar
      com.example.shared.util.DateFormatter

When both JARs are on the classpath, they can both contribute classes to the `com.example.shared.util` package of the unnamed module.

When turning each JAR into a separate named module on the module path, this package becomes split across named modules. A structure that worked on the classpath may no longer be valid when resolved as named modules.

This is why you need to audit packages before modularizing a legacy system. Do not simply add `module-info.java` to each JAR while ignoring packages shared across artifacts.

## 9. Automatic modules also obey module path rules

A JAR without `module-info.class`, when placed on the module path, can become an **automatic module**. The module name is usually derived from the JAR name or from the manifest if `Automatic-Module-Name` is declared.

An automatic module is still a named module in the module configuration. Its packages are inferred from the JAR contents; therefore, it can also participate in a split package conflict with another named module.

For example, if `legacy-util.jar` becomes automatic module `legacy.util` and contains package `com.example.shared.util`, while `com.example.shared` also contains that package, putting both into the same module configuration can cause a conflict.

Automatic modules have broader readability and export rules than explicit modules, but that does not mean they are exempt from the package constraints of a named-module configuration.

## 10. How to inspect when encountering a package error

When a module build or runtime reports a duplicate package error, inspect in order:

1. Identify the full package name in the error message, e.g. `com.example.shared.util`.
2. Identify the modules or JARs containing that package.
3. Determine which module should own the shared classes.
4. Move the shared classes into one module, or change the package of classes that are only for internal use.
5. Update `requires` and `exports` according to the new relationship.
6. Recompile and re-resolve all related modules.

You can inspect the descriptor of a modular JAR:

    jar --describe-module --file libs/example.jar

You can list the JAR contents to find packages:

    jar --list --file libs/example.jar

With a JDK supporting the module validation option, you can instruct the launcher to validate the module path:

    java --module-path mods --validate-modules

If the error only appears when switching from the classpath to the module path, inspect legacy dependency JARs and automatic modules first. A package may have already been split across multiple artifacts before the project adopted JPMS.

## 11. Common misconceptions

- **Thinking two different classes cannot cause a split package.** They still conflict if they declare the same package across two named modules.
- **Thinking renaming the module is enough.** Different module names do not make the package names different.
- **Thinking a subpackage is part of the parent package.** `com.example.api` and `com.example.api.internal` are two separate packages.
- **Thinking only exported packages count.** Package ownership does not depend on whether the package is exported.
- **Thinking automatic modules are exempt from package uniqueness.** An automatic module is still a named module on the module path.
- **Thinking a split package on the classpath proves the layout is valid on the module path.** The classpath groups JARs into the unnamed module; named modules have stricter ownership rules.
- **Thinking `exports` or `opens` fixes a split package.** These directives control access permissions, not which module owns a package.

## Key takeaways

Within the same module configuration, design so that each package has one clear owning named module. If multiple modules need to use classes in the same package, move that package into a shared module. If classes belong only internally to individual modules, separate them into distinct packages by responsibility.

When modularizing a legacy system, check both explicit modules and automatic modules on the module path, because split packages often only surface after JARs are placed into a named-module configuration.