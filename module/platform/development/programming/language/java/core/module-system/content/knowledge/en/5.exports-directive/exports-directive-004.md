# Exporting Public Types and Access Conditions

## 1. What Does exports Control?

In the Java Platform Module System (JPMS), a module can contain many packages serving different purposes: user-facing APIs, internal implementations, adapters, helpers, and test code. Without module access boundaries, users can easily depend directly on implementation classes that the module author intended to keep hidden.

The **exports** directive in the module descriptor specifies which packages are made public for other modules to access under normal Java rules.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

This declaration allows modules that read com.acme.customer to access public types belonging to package com.acme.customer.api, while keeping other packages of the module closed to normal Java access from outside.

Some points to remember:

- exports applies to the **entire package**, not selectively to individual classes or methods.
- The exports directive does not automatically make classes or members public.
- The module using the package must still have permission to read the module providing that package.
- Java language access rules such as public, protected, package-private, and private still apply.
- Subpackages are separate packages. Exporting com.acme.customer.api does not automatically export com.acme.customer.api.internal.

Therefore, exports is part of the module-level API contract. It defines the package surface that a module allows other modules to use.

## 2. Conditions for Accessing a Public Type

For code in module A to use a public type belonging to a package of module B, the primary conditions must all be satisfied simultaneously:

1. **Module B is resolved in the current configuration**: the providing module must be present in the application's module configuration.
2. **Module A reads module B**: typically declared using requires in A's module-info.java; readability can also come from requires transitive or additional runtime options.
3. **The package containing the type is exported to A**: B must export that package unconditionally or via a qualified export specifically to module A.
4. **The type and member being used have appropriate access levels**: the type must be public; the constructor, method, or field must permit access under Java rules.
5. **Other language conditions are valid**: parameter types, return types, enclosing types, inheritance, and protected access rules must also be valid.

This relationship can be visualized as follows:

~~~text
Module A (consumer)
    |
    | requires com.acme.customer
    v
Module B (provider)
    |
    | exports com.acme.customer.api
    v
Package com.acme.customer.api
    |
    | public type + public member
    v
Module A code is allowed to use the API
~~~

Having requires alone is not enough if the package is not exported. Conversely, an exported package is also not enough if the using module does not read the providing module.

## 3. Example of a Module with Public API and Internal Implementation

Suppose a customer management library has the structure:

~~~text
com.acme.customer/
├── module-info.java
└── com/
    └── acme/
        └── customer/
            ├── api/
            │   ├── Customer.java
            │   └── CustomerService.java
            └── internal/
                └── CustomerRepository.java
~~~

The module descriptor exports only the API package:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Public type in the API:

~~~java
package com.acme.customer.api;

public record Customer(String id, String name) {
}
~~~

Public service:

~~~java
package com.acme.customer.api;

public class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }
}
~~~

An implementation class located in the internal package:

~~~java
package com.acme.customer.internal;

public class CustomerRepository {
    public CustomerRepository() {
    }
}
~~~

The application module declares the dependency:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

And uses the API:

~~~java
package com.acme.application;

import com.acme.customer.api.Customer;
import com.acme.customer.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findById("C-100");

        System.out.println(customer.name());
    }
}
~~~

The application code compiles because:

- com.acme.application reads com.acme.customer through requires.
- com.acme.customer exports com.acme.customer.api.
- Customer and CustomerService are public types.
- findById and name are accessible public members.

If Main tries to import com.acme.customer.internal.CustomerRepository, the compiler will reject it because the internal package is not exported. The fact that class CustomerRepository is declared public does not change this result. A type's public modifier cannot cross the module boundary established by exports.

## 4. exports Does Not Replace public and Java Access Levels

JPMS adds a module-level boundary; it does not eliminate Java's member access system.

| Access Level | Meaning in Java | Can another module access via an exported package? |
|---|---|---|
| public | Accessible from appropriate places under Java rules | Yes, if the type and module conditions are valid |
| protected | Accessible within the package and under subclass rules | Only in contexts permitted by Java |
| package-private | Only within the same package | No |
| private | Only within the class/nest scope permitted by Java | No |

Example:

~~~java
package com.acme.customer.api;

public class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }

    protected void validateExtension() {
    }

    void resetCache() {
    }

    private void rebuildIndex() {
    }
}
~~~

If this package is exported:

- Other client modules can call findById on a valid instance.
- validateExtension still follows protected rules: code in another package can only access it in a subclass context permitted by Java.
- resetCache is package-private, so it cannot be called from another module.
- rebuildIndex is private, so it cannot be called directly from outside the class.

Similarly, exporting a package does not make a package-private class in that package public. The following example still prevents modules outside the package from using InternalMapper:

~~~java
package com.acme.customer.api;

class InternalMapper {
}
~~~

When designing an API, clearly identify which types and members are genuinely part of the public contract. Avoid increasing access levels just to bypass compile errors if the type is not meant for library users.

## 5. Qualified Exports: Exposing Only to Selected Modules

A module can export a package to all modules that read it or only to a specific group of named modules.

Unqualified export:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Any module that reads com.acme.customer can access public types in the API package under Java rules.

Qualified export:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to
        com.acme.application,
        com.acme.integration;
}
~~~

In this example:

- com.acme.customer.api is the API for every module reading the library.
- com.acme.customer.spi is exported only to com.acme.application and com.acme.integration.
- Other modules can read com.acme.customer, but cannot access the SPI package through normal access rules.

Qualified exports are useful when a module has a broad public API and some extension points intended only for known integration modules.

The target module list must use the exact module names declared in their descriptors. If a target module is renamed, the qualified export must also be updated.

Qualified exports do not automatically create a readability relationship. The target module still needs to read the source module, usually via requires. Restricted exporting and module reading are two independent conditions.

## 6. Exporting a Package Does Not Automatically Export Subpackages

In Java, packages do not have an access inheritance relationship based on name structure. Package com.acme.customer.api and com.acme.customer.api.internal are two distinct packages.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

The declaration above exports only com.acme.customer.api. It does not export:

- com.acme.customer.api.internal
- com.acme.customer.api.validation
- com.acme.customer.spi

If you want to expose additional packages, you need to declare them separately:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.api.validation;
}
~~~

You should not export all internal packages just because they sit beneath an API package. Exporting an additional package creates more compatibility surface that the module author must consider when changing library versions.

## 7. exports and requires transitive Have Different Roles

These two directives often appear together, yet they solve two different problems:

- **exports** determines which packages of the current module can be accessed by other modules.
- **requires transitive** propagates the readability relationship to a dependent module for modules that read the current module.

Example of an API module using a type from a model module in its public signature:

~~~java
module com.acme.customer.api {
    requires transitive com.acme.model;
    exports com.acme.customer.api;
}
~~~

The application module only needs to declare:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

Thanks to requires transitive, com.acme.application has a readability relationship to com.acme.model and can work with types exposed by the public API, provided the corresponding package of com.acme.model is also appropriately exported.

If you only write exports com.acme.customer.api without an appropriate readability relationship to com.acme.model, the consuming module may still run into issues when needing to reference types from the model module.

A way to remember:

~~~text
exports
    -> Opens a package of the current module to other modules.

requires transitive
    -> Propagates readability to a dependent module.
~~~

Do not use requires transitive just to "make it compile." Use it when the dependency genuinely appears in the public API or when API users need to read that module according to the designed contract.

## 8. exports and opens: API Access vs. Deep Reflection Access

exports is intended for normal Java access to public types and permitted members. It also supports public reflection on public members of public types within the exported package.

However, frameworks may need deep reflection to access private fields, private constructors, or private methods. In that case, the package needs to be opened with opens.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.internal to com.acme.persistence;
}
~~~

The declaration above means:

- API consumer modules can access public types in com.acme.customer.api.
- Module com.acme.persistence is permitted to perform deep reflection into package com.acme.customer.internal.
- The internal package still does not become a normal Java API for all modules.

You can open a package to all modules with:

~~~java
module com.acme.customer {
    opens com.acme.customer.internal;
}
~~~

Or declare the entire module as open:

~~~java
open module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

An open module opens all of its packages for deep reflection at runtime. In an open module descriptor, individual opens directives are not declared; if restricted opening is needed, use a normal module with specific opens lines.

| Directive | Normal Java Access | Deep Reflection |
|---|---|---|
| exports | Allowed according to Java public/protected levels | Allows normal public access |
| opens | Does not grant import/API call permission like exports | Allows deep access within the package |
| open module | Does not automatically export packages | Opens all packages for deep reflection |

If a framework reports InaccessibleObjectException when accessing a private member, check whether the package has been opened to the framework module via opens. Adding exports usually does not solve deep reflection requirements.

## 9. Adding Exports at Runtime via the Command Line

During migration or when diagnostics are needed, the Java launcher and compiler provide options to add exports without immediately modifying the module descriptor.

Example of opening an API package to a target module:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.internal=com.acme.application \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

General syntax:

~~~text
--add-exports source.module/package=target.module
~~~

ALL-UNNAMED can be used as the target when exporting a package to classes belonging to the unnamed module:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.internal=ALL-UNNAMED \
     -cp app.jar \
     com.acme.legacy.Main
~~~

For modular source code that needs to compile in a corresponding environment, javac also supports --add-exports. These additional configurations should be managed clearly in build or launch configurations.

These options are helpful for compatibility and diagnostics, but if a package is truly a long-term supported API, declare it in module-info.java. Avoid letting an application depend on a library's internal package simply because a command-line option opened access.

Note: --add-exports only opens normal Java access for the specified package. It does not replace --add-opens when a framework needs deep reflection into private members.

## 10. How to Check Whether an API Is Exported

When a public type cannot be imported from another module, check in the following order:

1. **Module name**: does the library's module descriptor declare the exact name that the consuming module uses in requires?
2. **Module path**: is the module containing the type found and resolved in the current compile/run?
3. **Package name**: does the package declared in source match the package exported by the module descriptor?
4. **Export type**: is the package exported unconditionally, or qualified-exported only to another module?
5. **Readability relationship**: does the consuming module require the providing module or receive a valid readability relationship?
6. **Java access level**: is the type public, and are any enclosing types and needed constructors/members accessible?
7. **Reflection**: if the error occurs inside a framework accessing private members, does the package need opens for the framework module?

You can view the descriptor of a modular JAR:

~~~bash
jar --describe-module --file mods/com.acme.customer.jar
~~~

The output shows the module name, exported packages, qualified exports, and dependency directives. This is a quick way to confirm that the distributed module has the expected descriptor.

You can ask Java to print module resolution at runtime:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

This output helps confirm which modules participate in the runtime configuration. If the providing module does not appear, review root modules, requires, and the module path before concluding the error lies in exports.

## 11. Common Errors and How to Handle Them

**Package is not exported**

The compiler may report that the package is not exported or that the module cannot read the package. Check the source module's module-info.java and add exports for the correct package and the appropriate target recipients if the design requires it.

**Type is public but still inaccessible**

The public keyword does not cross module boundaries. The package containing the type must be exported to the consuming module, and the consuming module must read the source module.

**Qualified export points to the wrong module**

If the line exports package to module-name uses the wrong name, the module needing access will not receive permission. Cross-check the name in the target module's module-info.java.

**Subpackage mistakenly assumed to be exported**

Exporting a parent package does not export subpackages. Declare each package belonging to the public API individually.

**Public API exposes types from an internal package**

A public method may return or accept a parameter belonging to an unexported package. External users will find it difficult to use that contract fully. Move the type that needs to be public into the API package or redesign the signature so it does not expose internal details.

**Framework cannot access private members**

exports does not grant deep reflection permission. Open the appropriate package using opens or an equivalent configuration for the framework module needing access.

**Opening too many packages**

Exporting or opening all internal packages increases the dependency surface and reduces the ability to change implementations. Export only packages belonging to the API contract and use opens only for frameworks that truly need reflection.

## 12. Module API Design Principles

When designing a module, divide packages by role:

~~~text
com.acme.customer/
├── com.acme.customer.api/          # Public API
├── com.acme.customer.spi/          # Controlled extension point
├── com.acme.customer.internal/     # Implementation
└── com.acme.customer.persistence/  # Persistence details
~~~

Then expose only the necessary packages:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to com.acme.application;
    opens com.acme.customer.persistence to com.acme.persistence;
}
~~~

Principles to apply:

- Keep the public API small, stable, and documented.
- Use qualified exports when only a few modules are permitted to integrate.
- Keep implementation packages unexported.
- Do not widen Java access levels just to work around module errors.
- Use opens separately for deep reflection needs, avoiding opening the entire module unless necessary.
- When a public API exposes types from another dependency, consider requires transitive based on the API contract.
- Verify the module descriptor of the actual artifact after packaging.

This design lets library users know which parts are supported long term, while authors can still change internal implementation packages and classes without breaking the published API.

## 13. Key Takeaways

- exports exposes a package at the module level; it does not automatically make types or members public.
- The consuming module must read the providing module, and the package must be exported to that module.
- Java access modifiers remain in effect: package-private and private do not become public via exports.
- Qualified exports restrict a package to specified target modules.
- Exporting a package does not automatically export subpackages.
- requires transitive propagates readability; exports opens a package of the current module. Both directives have distinct roles.
- opens is for deep reflection; exports does not replace opens.
- Use jar --describe-module to view descriptors and --show-module-resolution to observe the module configuration at runtime.

When encountering access errors in JPMS, determine whether it is a missing readability relationship, a missing export, an unsuitable Java access level, or a missing opens for reflection. Addressing the exact condition will keep the API clear and avoid opening access broader than needed.