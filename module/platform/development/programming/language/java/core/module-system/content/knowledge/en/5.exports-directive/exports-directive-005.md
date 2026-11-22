# Distinguishing exports from public in Source Code

In Java, the **`public`** keyword and the **`exports`** directive are both related to accessibility, yet they operate at two different layers. `public` is a Java language access rule for a type or member. `exports` is a module-level declaration allowing other modules to access public types belonging to a specific package.

Therefore, a class can be declared `public` and still be unusable by an external module if the package containing that class is not exported. Conversely, exporting a package does not turn classes or members with package-private, protected, or private access levels into public ones.

To understand this boundary properly, three conditions must be considered simultaneously: whether the consuming module reads the providing module, whether the package is exported to the consuming module, and whether the type/member satisfies Java access rules.

## 1. public Is a Java Language Access Rule

In Java source code, `public` is an access modifier. It can be used on top-level classes/interfaces, constructors, methods, fields, and other eligible members.

Example:

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }

    private String internalCode() {
        return "C-001";
    }
}
~~~

Considering Java language rules alone:

- The `Customer` class is public, so source code in another package can reference this class if the class is within a valid access scope.
- The `getName()` method is public, so it can be called from code that has access to the class.
- The `internalCode()` method is private, so only code within the Java-permitted scope of the `Customer` class can access it directly.
- A class or method being public does not automatically expose its containing package across a JPMS boundary.

Java access levels still apply when a project uses the module system. JPMS adds a layer of control at the package/module level; it does not replace language access modifiers.

## 2. exports Is Module-Level Package Exposure Permission

The `exports` directive is written in `module-info.java`:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

The declaration above states that module `com.acme.library` exposes package `com.acme.library.api` to other modules. When a consuming module reads the library module, it can access public types in the exported package, provided Java access rules also allow it.

`exports` applies to the entire named package. It does not list individual classes or methods. If you want to restrict which modules can use the package, you can use a qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.api to com.acme.application;
}
~~~

In this example, package `com.acme.library.api` is exported only to module `com.acme.application`. Another module, even if it declares `requires com.acme.library`, still cannot use this package across the module boundary.

## 3. Three Conditions for Another Module to Use a Public Type

Suppose the library module contains:

~~~java
// module-info.java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
// com/acme/library/api/Customer.java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }
}
~~~

The application module declares:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

Application code can use the class:

~~~java
package com.acme.application;

import com.acme.library.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer();
        System.out.println(customer.getName());
    }
}
~~~

Cross-module accessibility requires simultaneously satisfying:

1. **Readability:** the application module must read the library module. In the example, this is declared with `requires com.acme.library`.
2. **Export:** the library module must export the package containing the type. In the example, package `com.acme.library.api` is exported.
3. **Java access control:** the type and member being used must have appropriate access levels. Here, both the `Customer` class and the `getName()` method are public.

You can remember the rule as:

~~~text
consuming module reads providing module
        +
package is exported by source module
        +
type/member satisfies Java access modifiers
        =
code in consuming module can access the API
~~~

If one of the conditions above is missing, merely adding `public` to the class or merely adding `requires` to the application module is not enough to use the API.

## 4. public Does Not Replace exports

Consider a library module that does not export the package:

~~~java
module com.acme.library {
    // Do not export com.acme.library.api
}
~~~

A class in the package can still be declared public:

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }
}
~~~

Another module can declare `requires com.acme.library`, yet its source code is still not allowed to import `com.acme.library.api.Customer`. The reason is that the package has not been exported by the library module. The `public` keyword on `Customer` only satisfies the access condition at the language layer; it does not cross JPMS's encapsulation boundary.

When compiling the application, the compiler may report that the package is not exported or is not visible from the library module. If running a program compiled under a mismatched configuration, access can also fail at runtime. You should check the source module's descriptor, not just the class declaration.

A proper fix if the package is genuinely a public API is to add the directive:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

If the package is merely an implementation detail, keep it unexported and provide a public API in another exported package.

## 5. exports Does Not Make Every Type Public

The reverse direction is equally important. When a module exports a package, it only opens that package across the module boundary; access modifiers inside the package keep their original meaning.

Example:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
package com.acme.library.api;

public class Customer {
    public String getName() {
        return "An";
    }

    String getInternalLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }
}
~~~

A consuming module can instantiate `Customer` and call `getName()`. It cannot call `getInternalLabel()` because that method has package-private access; nor can it call `secret()` because that method is private.

Similarly, a top-level class not declared `public` does not become public just because the package is exported:

~~~java
package com.acme.library.api;

class InternalCustomerMapper {
    // Package-private top-level class
}
~~~

Other modules cannot import `InternalCustomerMapper`. Exporting a package does not bypass Java access rules.

Therefore, a module's API is defined by the combination of exported packages and the public types/members actually defined inside those packages. Do not treat `exports` as an operation that turns all contents of a package into API.

## 6. public, exports, and opens Have Different Roles

Three concepts are often confused:

| Mechanism | Scope | Effect |
|---|---|---|
| `public` | Java type/member | Permits access under Java language rules |
| `exports` | Package in module | Allows other modules to access public types in the package |
| `opens` | Package in module | Allows deep reflection into the package at runtime |

`exports` serves normal API access. `opens` serves reflection, such as when a framework needs to read or write private fields, invoke non-public constructors, or inspect metadata via reflection.

Example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Other modules can use public APIs in `com.acme.domain.api` if they read module `com.acme.domain`. Module `com.acme.json` is allowed deep reflection into `com.acme.domain.model`. Opening a package does not make types in that package public APIs for source code of other modules to import.

An exported package is also not opened by default for deep reflection into non-public members. If a framework needs deep access, declare `opens` separately for the appropriate package and target module.

## 7. Qualified Exports: Exposing Only to Selected Modules

A module can export a package to all modules or only to a target module list.

Unqualified export:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.spi to
        com.acme.plugin.alpha,
        com.acme.plugin.beta;
}
~~~

Qualified exports are useful when a module wants to let specific integration modules use an SPI while keeping that package away from other modules. Target module names must be valid module names in the configuration; merely declaring `requires com.acme.library` in an unlisted module does not grant access to the package.

For example, `com.acme.plugin.alpha` can import public types in `com.acme.library.spi` if it reads the library module. `com.acme.application` cannot import those types if it is not in the qualified export target list.

Qualified exports still do not alter access modifiers. A package-private class in `com.acme.library.spi` still cannot be imported from a plugin module.

## 8. Modules on the Classpath and the Unnamed Module

When a JAR is placed on the classpath, the JVM loads its classes into the unnamed module associated with the corresponding class loader. If the JAR contains `module-info.class`, that descriptor is ignored in normal classpath loading.

The unnamed module has different access rules from named modules: it reads modules in the boot layer, and packages of the unnamed module are exported/opened according to the corresponding mechanism. As a result, a public class on the classpath can be used by a traditional classpath application without `exports` in a descriptor.

This explains why a library may run when placed on the classpath yet encounter access errors after moving to the module path. When moved to the module path, the descriptor takes effect, and unexported packages are closed to external modules.

Do not use a classpath run result to conclude that the module descriptor exposes the API properly. Test running in an actual JPMS configuration.

## 9. Inspecting Exported Packages

Use `jar --describe-module` to view the descriptor inside a JAR:

~~~bash
jar --describe-module --file mods/com.acme.library.jar
~~~

The output may contain:

~~~text
com.acme.library jar:file:///.../com.acme.library.jar!/module-info.class
exports com.acme.library.api
requires java.base mandated
~~~

The line `exports com.acme.library.api` indicates the package is exported. If the package does not appear in the exports section, check `module-info.java` or the packaged descriptor.

You can use `javap` to inspect the binary descriptor:

~~~bash
javap --module-path mods --module com.acme.library module-info
~~~

This command helps verify the compiled directives. If you edited `module-info.java` but are still using an old JAR, the output may still reflect the old descriptor. Make sure you have recompiled and repackaged the right artifact before diagnosing.

## 10. Comprehensive Example and Error Cases

Suppose a library has three packages:

~~~text
com.acme.library
├── com.acme.library.api
├── com.acme.library.internal
└── com.acme.library.spi
~~~

Descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin;
}
~~~

Access results:

| Content | Plugin module | Other application module |
|---|---|---|
| Public class in `api` | Accessible if reading the library module | Accessible if reading the library module |
| Public class in `spi` | Accessible if reading the library module | Not accessible across module boundary |
| Public class in `internal` | Not accessible across module boundary | Not accessible across module boundary |
| Package-private class in `api` | Not accessible | Not accessible |
| Private member of public class | Not directly accessible per Java access control | Not directly accessible per Java access control |

Some common scenarios:

- **Public class, but package not exported:** code in another module cannot import the class across the JPMS boundary.
- **Package exported, but class is package-private:** other modules still cannot import that class.
- **Package exported, but member is private:** external code cannot call the private member under Java rules.
- **Module has requires, but package is not exported:** readability is present, but accessibility is insufficient.
- **Package is opened with opens, but not exported with exports:** frameworks can perform deep reflection as configured, yet source code in other modules still cannot use the package as a normal API.
- **JAR runs on classpath, but fails on module path:** check descriptors, requires, and exports; the classpath ignored the module descriptor.

## 11. Key Takeaways

`public` answers whether **a type or member is accessible under Java rules**. `exports` answers **which packages of a module are exposed to other modules**. To use a public type across modules, the consuming module must read the providing module, the package containing the type must be exported to that module, and the type/member must satisfy Java access modifiers.

`exports` does not turn package-private classes into public ones, does not turn private members into public ones, and `public` does not automatically open a package across JPMS. When designing module APIs, select the packages to export, keep internal packages unexported, use qualified exports for restricted SPIs, and use `opens` separately when a framework genuinely needs deep reflection.