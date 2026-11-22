# Qualified Exports for Specialized Integration

## 1. Objectives

The Java Platform Module System (JPMS) allows a module to expose its packages through the **exports** directive in the **module-info.java** file. An export does not have to be open to every module. When a package only serves specific integration systems, the source module can use a **qualified export** to specify the exact modules allowed to access it.

For example, a platform module can provide an integration package for a partner adapter module, a reporting module, and an internal testing module. Other modules remain unable to access that package via standard module rules.

After this lesson, you will be able to:
- Write the **exports package.name to module.one, module.two;** directive.
- Distinguish a qualified export from an unqualified export.
- Design an API package meant for a defined group of integration modules.
- Understand why consumers still need **requires** to read the providing module.
- Distinguish qualified exports from **opens**, **--add-exports**, and **--add-opens**.
- Diagnose module access errors and test integration scope.

## 2. What Is a Qualified Export?

A module can export a package in two ways.

An **unqualified export** exposes the package to every module that reads the source module:

~~~java
module com.example.platform {
    exports com.example.platform.api;
}
~~~

Every module that reads **com.example.platform** can access public types in the **com.example.platform.api** package, according to standard Java access rules.

A **qualified export** exposes the package only to the listed modules:

~~~java
module com.example.platform {
    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

In this example, the **com.example.platform.partner** package is exported to two target modules:
- **com.example.crm.adapter**
- **com.example.audit.integration**

Other modules not on the list still cannot access this package through the module system, even if they read **com.example.platform**.

A qualified export is a package-level directive. It does not select individual classes or methods within the package. If a package is exported to a target module, the public types in that package can be accessed by that target module under Java rules. Therefore, design the package so it only contains types that genuinely belong to the integration API.

## 3. Syntax in module-info.java

Syntax:

~~~java
exports package.name to module.name.one, module.name.two;
~~~

Components:

- **exports**: declares the package exposed across the module boundary.
- **package.name**: full package name, not a class name or directory path.
- **to**: marks this as a qualified export.
- **module.name.one** and **module.name.two**: target module names, separated by commas.

Example:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.partner
        to com.example.crm.adapter,
           com.example.billing.bridge;
}
~~~

Here:
- **com.example.orders.api** is a public API for every module reading **com.example.orders**.
- **com.example.orders.partner** is exported only to the two named integration modules.
- Other unexported packages remain closed to normal access from other modules.

Names in the **to** list are module names, not application package names. For example, if the consumer module declares:

~~~java
module com.example.crm.adapter {
    requires com.example.orders;
}
~~~

then the exact target module name is **com.example.crm.adapter**.

A qualified export only makes sense when the source module is a named module and the target modules are also identified by module names. Do not write **ALL-UNNAMED** in the **to** list. ALL-UNNAMED is a special target for launcher options such as **--add-exports**, not a valid module name to use in a module-info.java directive.

## 4. Complete Producer and Consumer Example

Suppose the **com.example.platform** module provides an API reserved for two integration modules.

Illustrative directory structure:

~~~text
src/
  com.example.platform/
    module-info.java
    com/example/platform/api/PlatformService.java
    com/example/platform/partner/PartnerGateway.java
  com.example.crm.adapter/
    module-info.java
    com/example/crm/adapter/CrmSync.java
  com.example.audit.integration/
    module-info.java
    com/example/audit/integration/AuditExport.java
  com.example.external.app/
    module-info.java
    com/example/external/app/Main.java
~~~

Source module:

~~~java
module com.example.platform {
    exports com.example.platform.api;

    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

General API:

~~~java
package com.example.platform.api;

public interface PlatformService {
    String platformName();
}
~~~

Dedicated integration API:

~~~java
package com.example.platform.partner;

public final class PartnerGateway {
    public String submit(String payload) {
        return "accepted: " + payload;
    }
}
~~~

CRM consumer module:

~~~java
module com.example.crm.adapter {
    requires com.example.platform;
}
~~~

Consumer code:

~~~java
package com.example.crm.adapter;

import com.example.platform.partner.PartnerGateway;

public final class CrmSync {
    public String synchronize() {
        PartnerGateway gateway = new PartnerGateway();
        return gateway.submit("customer-42");
    }
}
~~~

The audit module is also allowed to read the integration package because it is in the qualified export list:

~~~java
module com.example.audit.integration {
    requires com.example.platform;
}
~~~

Meanwhile, an unlisted module:

~~~java
module com.example.external.app {
    requires com.example.platform;
}
~~~

If this module tries to import **com.example.platform.partner.PartnerGateway**, the compiler will report that the package is not exported to **com.example.external.app**. Having **requires com.example.platform** only makes the source module readable; it does not automatically grant access to every package inside that module.

## 5. Qualified Exports Do Not Replace requires

For a consumer module to use a public type in an exported package, two conditions must be satisfied:

1. The consumer must read the source module.
2. The package containing the public type must be exported to the consumer.

Usually, the consumer declares **requires** in its module descriptor:

~~~java
module com.example.crm.adapter {
    requires com.example.platform;
}
~~~

The source module declares a qualified export:

~~~java
module com.example.platform {
    exports com.example.platform.partner
        to com.example.crm.adapter;
}
~~~

These two directives work together:
- **requires** lives in the consumer and establishes a readability relationship to the source module.
- **exports ... to ...** lives in the source module and allows the target module to access the specified package.

If **requires** is missing, the consumer cannot read the source module even though the package is exported to it. If the consumer name is missing from the **to** list, the consumer can read the source module but still cannot access the package.

When you have to configure the module graph from the command line without editing the descriptor, you can consider **--add-reads** to add readability. This is a workaround for runtime configuration; for a stable integration, express the dependency using **requires** in module-info.java.

## 6. When Should You Use Qualified Exports?

A qualified export fits when a package is an intentional integration API rather than a general API for the entire module ecosystem.

Some scenarios:

- **Partner adapters:** only partner-provided adapter modules are allowed to use the integration API.
- **Bridge between two systems:** a bridge module needs certain types to convert data or protocols.
- **Controlled plugins:** a known set of plugin modules need to use a dedicated extension API.
- **Internal API between modules in the same product:** the development team wants to separate the stable public API from a package meant for specific collaborating components.
- **Migration integration:** a legacy module needs access to a transitional package while newer modules already use a different public API.

Do not use a qualified export just because you want to "hide" a class from users within the same module. If a class is not an API, put it in an unexported package. A qualified export is a tool to control which modules can access a package, not a tool to select classes inside a package.

If many external modules need the package as a long-term public contract, an unqualified export may be simpler and more appropriate. If only a few managed integration modules need that package, a qualified export accurately expresses the dependency scope.

## 7. Designing a Package Dedicated to Integration

Because a qualified export applies to an entire package, how packages are organized determines the exposed API scope.

For example, separate the public API, integration API, and implementation:

~~~text
com.example.platform.api
com.example.platform.partner
com.example.platform.internal
com.example.platform.impl
~~~

Module descriptor:

~~~java
module com.example.platform {
    exports com.example.platform.api;

    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

In this organization:
- **api** contains types that any valid consumer can use.
- **partner** contains types shared with selected integration modules.
- **internal** and **impl** are not exported and thus stay within the module boundary.

Avoid placing public implementation classes in a qualified-exported package if consumers do not need them. Even if consumers are discouraged from using them, public classes in an exported package can still become part of the API surface that the source module must consider maintaining.

A good design usually provides a small interface or facade instead of letting integrations access many implementation classes. For example, export only **PartnerGateway** and the necessary request/response data types; keep caches, repositories, internal factories, and implementations in unexported packages.

## 8. How Qualified Exports Differ from opens

**exports** and **opens** address two different kinds of access.

| Directive | Effect | Common Use Case |
|---|---|---|
| **exports p** | Allows modules reading the source to access public types/members in package p under Java rules | API called directly via code |
| **exports p to m** | Allows only module m to access the public API of package p | Integration API meant for specific modules |
| **opens p** | Allows deep reflection into package p at runtime | Frameworks needing reflective access to non-public members |
| **opens p to m** | Opens package p only for deep reflection from module m | Controlled reflection by a framework or adapter |

Example of a qualified open:

~~~java
module com.example.persistence {
    opens com.example.persistence.entity
        to com.example.orm;
}
~~~

This example allows the **com.example.orm** module to perform deep reflection on the entity package under reflection rules. It is not equivalent to a qualified export.

If the integration directly calls a public method on **PartnerGateway**, use a qualified export. If a framework needs to access private fields or private constructors via reflection, evaluate a qualified open. Do not add both **exports** and **opens** when only one permission is enough.

An exported package is not automatically open for deep reflection into private members. Conversely, a package opened for reflection does not mean consumer code can import all public types in the package in the standard way.

## 9. How Qualified Exports Differ from --add-exports

Exports can be added via a launcher option:

~~~bash
java --add-exports com.example.platform/com.example.platform.partner=com.example.crm.adapter --module-path mods --module com.example.crm.adapter/com.example.crm.adapter.Main
~~~

This option adds an export to the JVM process's module configuration. It does not edit **module-info.java** and does not alter the module descriptor inside the JAR.

Comparison:

- **Qualified export in module-info.java:** part of the source module's design, packaged into the descriptor, and applied when the module is resolved.
- **--add-exports:** a command-line override, typically used for migration, testing, or special deployment environments.
- **--add-opens:** opens a package for deep reflection at runtime; does not replace a qualified export.

If you own the source module, prefer expressing long-term integration relationships in **module-info.java**. Use command-line flags when you need an intentional operational adjustment or when you cannot modify the module descriptor.

The **--add-exports** option also does not automatically create readability. If the consumer does not read the source module, **requires** or an appropriate **--add-reads** configuration is needed.

## 10. Limitations and Considerations

A qualified export narrows the set of modules allowed to access a package, but it is not a security mechanism replacing application authentication or authorization.

Some points to keep in mind:

1. **Scope is the package:** all public types in the package can become API surface for the target modules.
2. **The module name is a contract:** renaming a consumer module can cause the qualified export to stop matching.
3. **Readability is still needed:** a qualified export does not add **requires** to the consumer.
4. **Reflection is a separate concern:** accessing private members via reflection may require **opens**, not **exports**.
5. **Not a sandbox:** the module system aids encapsulation and controls accessibility per module; it does not replace security controls, plugin identity verification, or data authorization.
6. **The API still needs versioning:** modules exported to can depend on public types; changing signatures or removing types can break the integration.
7. **Avoid split packages:** do not scatter classes of the same package across multiple named modules. Clear package ownership makes module resolution predictable.

If a target module is absent from the module graph, the qualified export is still recorded in the descriptor but creates no access for a consumer that is not present. When the target module is included in the graph in another run, the export relationship takes effect for that module.

## 11. Compiling and Running the Example

Suppose the modules are placed in the **src** directory following the structure in the example section. You can compile the modules together using the module source path:

~~~bash
javac --module-source-path src -d mods -m com.example.platform,com.example.crm.adapter,com.example.audit.integration
~~~

If you want to inspect the module graph, use:

~~~bash
java --module-path mods --describe-module com.example.platform
~~~

Run the consumer module:

~~~bash
java --module-path mods --module com.example.crm.adapter/com.example.crm.adapter.Main
~~~

If the consumer is allowed to access the partner package, the module graph resolves and the code can use public types in that package. If another module not in the qualified export list tries to import the same type, an error can occur at compile time or at runtime linking/access, depending on when it is checked.

For a packaged JAR artifact, you can inspect the descriptor with:

~~~bash
jar --describe-module --file platform.jar
~~~

The module description helps confirm the module name and exported packages. Use **jdeps** or module analysis tools to inspect dependencies if needed.

## 12. Diagnosing Qualified Export Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Consumer reports package is not exported | Target module is not listed in the qualified export | Add the exact consumer module name to the **to** list |
| Consumer reports module does not read source module | Missing **requires** or readability | Declare requires or check the module graph |
| **to** directive reports module not found | Target module name is wrong or module is not on the module path at compile time | Check the name in module-info.java and the compile configuration |
| Consumer on classpath cannot access | Unnamed module cannot be listed as a target in a module descriptor | Use a named module for integration or temporarily configure --add-exports |
| Framework cannot access private fields | Package is only exported, not opened for deep reflection | Consider **opens p to m** or --add-opens |
| Another module can still access the package | Package also has an unqualified export or a command-line override | Check module-info.java and JVM arguments |
| Integration fails after renaming a module | Qualified export still targets the old module name | Synchronize the module name in the descriptor and dependencies |

When investigating, check both sides: the source module's descriptor and the consumer's descriptor. Identify the exact package, module name, **requires**, **exports ... to ...**, and JVM flags passed to the process. Do not just look at the consumer's source code and assume the problem lies in the public modifier.

## 13. Self-Check

**1. Which modules are allowed to access the package by the directive exports com.example.partner to com.example.crm;?**

Only the module named **com.example.crm** is exported that package, provided the consumer reads the source module and follows standard Java access rules.

**2. Does a qualified export automatically add requires to the consumer module?**

No. The consumer must still read the source module, usually via a **requires** directive in module-info.java.

**3. Can ALL-UNNAMED be listed in the module list after the to keyword?**

No. **ALL-UNNAMED** is a special target for command-line options such as **--add-exports**, not a module name used in a qualified export in a module descriptor.

**4. If a framework needs to read private fields via reflection, is a qualified export enough?**

No. Deep reflection requires the package to be opened with **opens** or an equivalent runtime mechanism such as **--add-opens**.

**5. Is a qualified export a security mechanism to restrict malicious plugins?**

No. It controls package accessibility across modules; it does not replace plugin verification, sandboxing, or application-layer authorization.

**6. Why should the partner package be separated from the implementation package?**

Because a qualified export applies to the entire package. Separating packages ensures only the necessary integration types are exposed while keeping the implementation inside the module.

## 14. Key Takeaways

A qualified export is how a source module exposes a package to a specific list of target modules. It is useful for specialized integration when certain adapters or bridges need a dedicated API while other modules do not need access to that package.

Place the **exports ... to ...** directive in the source module's module-info.java, declare **requires** in the consumer, and organize packages to match the API surface to be shared. Use **opens** for deep reflection and treat **--add-exports** as an intentional runtime/compile-time override. Qualified exports improve encapsulation, but do not replace application authentication or security authorization.

## References

- [Java Language Specification — Module Declarations, Exports](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2)
- [The Java Module System — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
