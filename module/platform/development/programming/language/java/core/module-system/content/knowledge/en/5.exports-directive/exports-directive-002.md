# Unexported Packages and Encapsulation

In JPMS, a package is the unit that a module can expose to the outside. A package can contain public classes and still remain inaccessible to other modules if the owning module does not declare **exports**. This rule helps a module keep its implementation internal and expose only the packages that truly belong to the API for consumers.

Learning how to use unexported packages is an important step in understanding JPMS encapsulation. It is necessary to distinguish Java language-level access from module-level access: the **public** modifier on a class does not automatically make a package part of the module's public API.

## 1. What Does an Unexported Package Mean?

A named module is described by **module-info.java**. The **exports** directive specifies the packages that a module allows other modules to access as API.

Example:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Suppose the module has the following packages:

~~~text
com.acme.billing
├── module-info.java
└── com/acme/billing
    ├── api/
    │   └── InvoiceService.java
    └── internal/
        ├── InvoiceRepository.java
        └── InvoiceCalculator.java
~~~

Here, the module only exports **com.acme.billing.api**. The package **com.acme.billing.internal** is not exported, so code belonging to other modules cannot use types in that package as a normal Java API.

This remains true even if a class in the internal package is declared **public**:

~~~java
package com.acme.billing.internal;

public class InvoiceCalculator {
    public long calculateTotal(long subtotal, long tax) {
        return subtotal + tax;
    }
}
~~~

The **public** modifier indicates the class's access level under Java language rules. JPMS adds another layer of control: whether the module containing that package exposes the package to the calling module. Because the package **com.acme.billing.internal** is not exported, another named module cannot import and use **InvoiceCalculator** simply by declaring **requires com.acme.billing**.

## 2. Combining Readability and exports

For the application module to use the billing module's API, it needs to declare a dependency:

~~~java
module com.acme.application {
    requires com.acme.billing;
}
~~~

Application code can use types in the exported package:

~~~java
package com.acme.application;

import com.acme.billing.api.InvoiceService;

public class Checkout {
    private final InvoiceService invoiceService;

    public Checkout(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }
}
~~~

If the application tries to import a class in the internal package:

~~~java
import com.acme.billing.internal.InvoiceCalculator;
~~~

the compiler will report that the package or type is not accessible because module **com.acme.billing** does not export that package to **com.acme.application**.

The two conditions must be understood separately:

1. **Readability:** the calling module must read the module providing the type, typically via the **requires** directive.
2. **Accessibility at module boundary:** the package containing the type must be exported by the providing module to the calling module.

Having **requires** does not mean the calling module can access every package of the dependency. **requires** creates the dependency and readability relationship; **exports** determines which packages are exposed.

## 3. Two-Layered Encapsulation

Java already has language-level access levels:

- **private:** members are accessible only within the class scope under Java rules.
- **package-private:** members with no modifier declared are accessible only within the same package.
- **protected:** allows access under package and inheritance rules.
- **public:** allows access under Java rules, provided the relevant module boundaries also allow it.

JPMS adds a module boundary outside those rules. A public type in an unexported package still cannot be used as an API by an external named module.

| Control Layer | Question Answered | Mechanism |
|---|---|---|
| Java types and members | Is the class or member public, protected, package-private, or private? | Java access modifiers |
| Module dependency | Does the current module read the module providing the type? | **requires**, **requires transitive** |
| Package exposure | Is the package open for normal Java access from other modules? | **exports** |
| Deep reflection | Can a framework module access non-public members via reflection? | **opens** |

Therefore, JPMS encapsulation does not replace Java modifiers. It adds a boundary at the package/module level, helping module authors control the API surface before class and member access rules are applied.

## 4. Code Inside the Module Still Uses Unexported Packages

An unexported package is not a disabled package. Classes belonging to the same module can still use each other under normal Java access rules.

For example, **InvoiceService** is the module's public API and can call the internal implementation:

~~~java
package com.acme.billing.api;

import com.acme.billing.internal.InvoiceCalculator;

public class InvoiceService {
    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    public long total(long subtotal, long tax) {
        return calculator.calculateTotal(subtotal, tax);
    }
}
~~~

The code above is valid when both packages belong to the same module **com.acme.billing**. The **internal** package does not need to be exported for code in the same module to access it.

This design creates a clear usage path:

- Consumers depend on **com.acme.billing.api**.
- The module's API calls the implementation in **com.acme.billing.internal**.
- Consumers do not depend directly on implementation classes.
- Module authors can change or replace internal implementations without having to maintain compatibility for external consumers.

Not exporting a package also does not mean classes or files in that package are removed from the JAR. The classes are still compiled and packaged; the module system controls accessibility between modules.

## 5. Whole-Package Exports and Qualified Exports

If a package needs to be used by every module that reads the current module, an unqualified export can be used:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

If a package serves only a specific consumer, **qualified exports** can be used:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.internal.spi
        to com.acme.application;
}
~~~

In this example:

- Modules reading **com.acme.billing** can access package **com.acme.billing.api**.
- Only module **com.acme.application** can access package **com.acme.billing.internal.spi**.
- Other modules still cannot use this SPI package as an API.

Qualified exports are suitable for internal SPIs between modules within the same system, or for a designated framework/module that needs to call a supporting package. The target module name must match the actual module name in the consumer's descriptor.

You should not use qualified exports just to work around a poorly understood dependency error. Identify which module truly needs the package and why that package must become part of the contract between the two modules.

## 6. Unexported Packages and Reflection

Reflection has its own rules when crossing module boundaries. A framework may need to access non-public fields, constructors, or methods to map objects, serialize data, or inject dependencies.

**exports** primarily allows normal Java API access. To allow deep reflection into an internal package, the module can declare **opens**:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    opens com.acme.billing.internal to com.acme.orm;
}
~~~

Module **com.acme.orm** is allowed to perform deep reflection on types in package **com.acme.billing.internal** at runtime. This package still does not become a package that can be freely imported at compile time.

Forms of opening packages:

| Directive | Scope |
|---|---|
| **opens package.name;** | Opens the package for deep reflection from other modules at runtime. |
| **opens package.name to framework.module;** | Opens the package only to the specified module. |
| **open module module.name { ... }** | Opens all packages of the module for deep reflection at runtime. |

If a framework calls **setAccessible(true)** on a non-public member of a package that has not been properly opened, the JVM may throw **InaccessibleObjectException**. With **trySetAccessible()**, the result may be **false** when access is not permitted. APIs such as **MethodHandles.privateLookupIn** must also satisfy the corresponding package opening and readability conditions.

Open only the right packages to the right frameworks. Opening an entire module with **open module** has a broader scope and reduces the benefits of keeping implementations internal.

## 7. Complete Example: Public API and Internal Implementation

Suppose the billing module provides invoice total calculation functionality. The public API does not expose the calculator class:

~~~java
// module-info.java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

~~~java
// com/acme/billing/api/InvoiceService.java
package com.acme.billing.api;

import com.acme.billing.internal.InvoiceCalculator;

public class InvoiceService {
    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    public long total(long subtotal, long tax) {
        return calculator.calculateTotal(subtotal, tax);
    }
}
~~~

~~~java
// com/acme/billing/internal/InvoiceCalculator.java
package com.acme.billing.internal;

public class InvoiceCalculator {
    public long calculateTotal(long subtotal, long tax) {
        return subtotal + tax;
    }
}
~~~

The application module simply declares the dependency and uses the API:

~~~java
// module-info.java
module com.acme.application {
    requires com.acme.billing;
}
~~~

~~~java
// com/acme/application/Main.java
package com.acme.application;

import com.acme.billing.api.InvoiceService;

public class Main {
    public static void main(String[] args) {
        InvoiceService service = new InvoiceService();
        System.out.println(service.total(1000, 80));
    }
}
~~~

The application can compile and run because **com.acme.billing.api** is exported. If you replace the import in the application with **com.acme.billing.internal.InvoiceCalculator**, the compiler will reject access to the internal package.

This is how encapsulation is used to keep the implementation changeable independently of consumers. Consumers know the **InvoiceService** contract; the billing module owns the calculation logic and internal helper classes.

## 8. When Is It Necessary to Temporarily Open a Package from the Command Line?

During legacy application migration or error investigation, it is sometimes necessary to grant temporary access without modifying the descriptor right away. The JDK provides launcher/compiler options:

- **--add-exports** adds package export access to a target module.
- **--add-opens** adds permission to open a package for deep reflection at runtime.

Example, granting normal Java access to an internal package for a tooling module:

~~~bash
java --module-path mods   --add-exports com.acme.billing/com.acme.billing.internal=com.acme.tools   -m com.acme.tools/com.acme.tools.Inspector
~~~

Example, opening a package for reflection from a framework:

~~~bash
java --module-path mods   --add-opens com.acme.billing/com.acme.billing.internal=com.acme.orm   -m com.acme.application/com.acme.application.Main
~~~

If the consumer resides on the classpath, the target **ALL-UNNAMED** can be used. When compiling code that needs to access the package, the **--add-exports** option can also be passed to **javac**.

These options are useful for migration, testing, or diagnostics. Once the necessary relationships are identified, consider putting the appropriate access permissions into the descriptor using **exports**, qualified exports, or **opens**. You should not maintain an arbitrary list of extensions because it makes module boundaries difficult to understand and control.

## 9. Service Providers Can Reside in Unexported Packages

A useful case is when a module provides an implementation of a service without wanting consumers to depend on the package containing the provider.

Plugin module example:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.internal.CsvReportExporter;
}
~~~

The package **com.acme.csv.internal** does not need to be exported. The application module only needs to read the SPI module and declare **uses** for the corresponding service. It locates providers via **ServiceLoader**, without needing to import the implementation class.

This helps keep the provider implementation inside the module. Consumers only know the **ReportExporter** interface, while the provider can change its implementation class or package without exposing those details externally.

For this mechanism to work, the provider must comply with JPMS/ServiceLoader provider rules, the module containing the provider must be resolved into the layer being searched, and the service type must be the same API type used by the host.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Compiler reports package is not visible despite having **requires** | The dependency module does not export the required package. | Check **exports** or qualified exports in the providing module's descriptor. |
| Public class still cannot be imported | Public only resolves Java-level access; the package is not exported. | Export the right API package or redesign the consumer to use the exposed API. |
| Framework throws **InaccessibleObjectException** | The package needing deep reflection is not opened to the framework. | Use **opens package to framework.module** or configure a restricted **--add-opens**. |
| Module A can use the API, but module B cannot | Qualified export allows only the specified target modules. | Check the consumer module names in the **exports ... to ...** directive. |
| Consumer depends on an implementation class | The implementation was placed in an API package, or an internal package was exported too broadly. | Move the implementation to an unexported package and expose a stable interface/facade. |
| ServiceLoader does not find the provider | The provider module was not resolved, or the descriptor declared the wrong service/provider. | Check **uses**, **provides**, the service type, and the layer being searched. |

When debugging, identify which layer the error belongs to: Java access modifier, readability, export, or deep reflection. Then inspect the corresponding descriptor and target module. Adding broad permissions just to make an error disappear can mask an unreasonable dependency design.

## 11. Practice Exercises

1. Create module **com.acme.billing** with two packages **api** and **internal**. Export only the **api** package.
2. Create module **com.acme.application** declaring **requires com.acme.billing**. Use a public class in the API package and run the application.
3. Try importing a public class in the **internal** package from the application. Observe the compiler error and explain why the public modifier is not enough.
4. Move the implementation call into a facade in the API package. Confirm that the application does not need to know about the internal class.
5. Add a framework module simulating reflection. Compare behavior when the internal package does not have **opens** and when the package is opened with restrictions.
6. Create a service interface in an SPI module and a provider in an unexported package. Locate the provider using **ServiceLoader** from the application.
7. Try **exports package to module** with a specified consumer, then rename the consumer module to observe the access error.
8. Use **--add-exports** or **--add-opens** in a diagnostic run, then move the necessary permissions into the descriptor if it is a long-term contract.

## 12. Design Principles to Remember

- Exporting a package means accepting that package as part of the module's API surface.
- A public class in an unexported package can still be an internal implementation.
- Code within the same module still uses unexported packages under normal Java rules.
- **requires** and **exports** answer two different questions: whether a module reads a dependency, and which packages of the dependency are exposed.
- **opens** serves deep reflection at runtime; it does not replace exports for importing APIs at compile time.
- Qualified exports/opens should specify only the modules that truly need access.
- An internal package is not a security sandbox; it is the encapsulation boundary of the Java module system.

When designing a module, start from the APIs that consumers need to use, export those packages, and keep implementation packages unexported. This organization reduces coupling, preserves the ability to change implementations, and makes contracts between modules clearer.