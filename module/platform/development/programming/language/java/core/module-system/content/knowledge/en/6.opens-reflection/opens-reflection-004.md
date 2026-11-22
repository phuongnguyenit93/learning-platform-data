# Distinguishing opens from exports

In the Java Platform Module System (JPMS), both **exports** and **opens** appear in **module-info.java**, but they grant two different types of access permissions. **exports** exposes a package so other modules can use its public types under normal Java access rules. **opens** allows specified modules to perform deep reflective access to types and members in a package at runtime.

Accurately distinguishing these two directives is crucial when designing APIs and integrating frameworks. A package can be exported to serve as a public API, opened so a framework can read or modify object state via reflection, or configured with both if there are separate needs for each type of access.

## 1. exports exposes a public API

A module typically contains API packages that other modules are permitted to use. The **exports** directive exposes that package:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Suppose the API package has a type:

~~~java
package com.acme.domain.api;

public final class Customer {
    private final String id;

    public Customer(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
~~~

The consuming module needs to read the domain module:

~~~java
module com.acme.application {
    requires com.acme.domain;
}
~~~

Then application source code can import and call the public API:

~~~java
package com.acme.application;

import com.acme.domain.api.Customer;

public final class CustomerService {
    public String customerId() {
        Customer customer = new Customer("C-100");
        return customer.id();
    }
}
~~~

If the package **com.acme.domain.api** is not exported, the application module cannot access types in that package through normal Java usage, even if the class or method has the **public** modifier.

**exports** does not make every member of a package public. Java access rules still apply: the consuming module can use public types and appropriate public/protected members, but cannot access private fields or private methods solely because the package is exported.

## 2. opens allows deep access via reflection

Reflection allows a program to inspect classes, fields, methods, and constructors at runtime. Many frameworks use reflection to instantiate objects, map data, inject dependencies, read annotations, or access non-public fields.

In JPMS, packages of a named module are sealed against deep reflective access from other modules unless the package is opened. The **opens** directive opens a package for reflection:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity;
}
~~~

With this declaration, other modules can perform deep reflection into the package **com.acme.domain.entity** at runtime, according to JPMS rules. However, this package is not exposed as an API for source code in other modules to import and use classes directly. **opens** does not replace **exports**.

Example of an entity with a private field:

~~~java
package com.acme.domain.entity;

public class CustomerEntity {
    private String email;

    public CustomerEntity(String email) {
        this.email = email;
    }
}
~~~

A framework or reflection snippet can obtain the field and request deep access permission:

~~~java
Field field = CustomerEntity.class.getDeclaredField("email");

if (field.trySetAccessible()) {
    Object value = field.get(entity);
    System.out.println(value);
}
~~~

If the module containing the entity has not opened the corresponding package to the module invoking reflection, **trySetAccessible()** can return **false**. With **setAccessible(true)**, the JVM can throw **InaccessibleObjectException** when module access rules do not permit enabling access.

The purpose of **opens** is to support controlled runtime access. It does not grant permission to call package-private/private classes or methods in normal Java source code.

## 3. Comparing exports and opens

| Aspect | exports | opens |
|---|---|---|
| Purpose | Exposes an API for normal Java access. | Allows deep reflection at runtime. |
| Critical timing | Compile time and runtime. | Runtime reflection. |
| Public types/members | Modules that read it can access them under normal Java rules. | Can be inspected via reflection; does not automatically create source code access. |
| Private members | Does not grant private access. | Allows reflection to bypass access checks when the caller and runtime satisfy JPMS rules. |
| ORM/serialization frameworks | May be needed if the framework uses a public API. | Usually needed when the framework reads/writes non-public fields or constructors. |
| Interchangeable? | No. | No. |

You can remember by goal: **exports** is for API consumers; **opens** is for reflection mechanisms. A package may need both if it both provides a public API and allows frameworks to deeply access internal state.

## 4. Qualified exports and qualified opens

Packages do not always need to be opened or exported to all modules. JPMS supports restricting access to a specific list of modules.

### Qualified exports

Syntax:

~~~java
module com.acme.domain {
    exports com.acme.domain.spi to com.acme.plugin, com.acme.adapter;
}
~~~

Only the named modules receive permission to access the package **com.acme.domain.spi** via export rules. Other modules, even if they read **com.acme.domain**, cannot use that package as a normal API.

Qualified exports is suitable for SPIs or internal APIs shared among a known set of modules, such as a plugin host and official adapters.

### Qualified opens

Syntax:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

Only the module **com.acme.orm** is permitted to perform deep reflection into the entity package. Other modules do not receive this permission merely because they read domain.

Qualified opens is usually suitable when the application uses a specific ORM or serializer framework. Opening the package to the exact module helps limit the reflection surface and avoid granting unnecessarily broad permissions.

The target module name in a qualified directive must be a valid JPMS module name matching the actual module on the module path. If a framework runs in the unnamed module on the classpath, you cannot write **ALL-UNNAMED** as a target name in **opens ... to ...** in the descriptor; in that case, the runtime option **--add-opens** may be needed.

## 5. Example of ORM framework integration

Suppose an application has two modules:

- **com.acme.domain** owns entities and business logic.
- **com.acme.persistence** contains the ORM adapter.

Domain module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.persistence;
}
~~~

Persistence module:

~~~java
module com.acme.persistence {
    requires com.acme.domain;
    requires some.orm.framework;
}
~~~

The package **com.acme.domain.api** is exported so the application or adapter can call the public API. The package **com.acme.domain.entity** is opened only to persistence so the ORM can read annotations, instantiate entities, or map private fields via reflection.

If persistence needs to directly reference entity classes in source code, the entity package must also be exported appropriately, for example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.entity to com.acme.persistence;
    opens com.acme.domain.entity to com.acme.persistence;
}
~~~

Here, the two directives address two separate needs: qualified exports allows persistence code to use public types in the entity package; qualified opens allows the ORM to perform deep reflection into that package. If the adapter only needs reflection and does not reference entity classes directly in source code, only opens may be needed, depending on how the framework discovers and loads entities.

You should not open the entire domain just because a framework needs to access a few entities. Identify which package contains the types to be mapped and open only that package to the module that actually needs permission.

## 6. open module and per-package opens

JPMS provides two levels of package-opening configuration.

Opening a specific package:

~~~java
module com.acme.domain {
    opens com.acme.domain.entity;
    opens com.acme.domain.value;
}
~~~

Only the listed packages are opened for deep reflection from other modules.

Opening all packages of a module:

~~~java
open module com.acme.legacy {
    requires some.framework;
    exports com.acme.legacy.api;
}
~~~

An **open module** makes all packages in the module open for deep reflection at runtime. That does not mean all packages are exported for normal source code access. The module still needs **exports** directives if it wants to expose APIs to other modules.

Using an open module can be convenient when migrating a legacy application that relies heavily on reflection. However, it significantly widens the scope of packages that other modules can deeply access. For new libraries or systems, prefer per-package **opens** and per-module qualified opens.

An open module does not declare separate **opens** directives in its descriptor; the **open** keyword itself applies to every package. **exports** directives can still be declared to define the public API.

## 7. Does exports allow reflection?

Normal reflection must be distinguished from deep reflection.

When a package is exported to a module, that module can access public classes and public members under Java rules. Reflection can also inspect and invoke accessible public components. However, export does not allow the caller to bypass access checks to read or write private fields, invoke private methods, or call non-public constructors.

For example, an exported package:

~~~java
module com.acme.user {
    exports com.acme.user.api;
}
~~~

Class:

~~~java
package com.acme.user.api;

public class User {
    private String token;

    public String username() {
        return "alice";
    }
}
~~~

A consuming module can use **User.username()**. However, calling:

~~~java
Field token = User.class.getDeclaredField("token");
token.setAccessible(true);
~~~

can fail because the package is not opened to the caller module. To allow deep reflection, the providing module needs to declare **opens com.acme.user.api to ...** for the caller module, or use an open module if the intent is to open all packages.

This ensures public APIs remain protected from arbitrary deep access to internal state, even when the package is exported.

## 8. The --add-opens and --add-exports options

During migration or framework troubleshooting, you may need to grant access from the command line without editing the descriptor yet. The **--add-opens** option has the form:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.entity=com.acme.persistence \
     --module-path mods \
     --module com.acme.application
~~~

The left side of the equals sign is the source module and package; the right side is the target module receiving deep reflection permission. **ALL-UNNAMED** can be used as the target when the caller resides in the unnamed module, such as a framework running on the classpath:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.entity=ALL-UNNAMED \
     -cp "lib/*" com.acme.legacy.Main
~~~

The **--add-exports** option has a similar form, but grants package access under export rules:

~~~bash
java --add-exports com.acme.domain/com.acme.domain.internal=com.acme.adapter \
     --module-path mods \
     --module com.acme.application
~~~

**--add-exports** does not grant deep reflection into private members; **--add-opens** does not turn a package into an API that can be imported in source code. These are two distinct permissions.

These options are suitable as temporary compatibility workarounds, for testing, or for intentional runtime configurations. For libraries controlled by your team, stable access requirements should be placed in the descriptor rather than forcing every consuming application to remember to add JVM arguments.

## 9. Common errors when using reflection in named modules

| Symptom | Possible cause | Resolution |
|---|---|---|
| **InaccessibleObjectException** when calling setAccessible(true) | The source module's package is not opened to the caller module. | Add qualified **opens** or configure **--add-opens** for the right module/package. |
| **trySetAccessible()** returns false | JPMS does not allow the caller to enable deep access to the member. | Check the caller module and opens permissions; do not assume a public class means private fields are accessible. |
| **package is not visible** when importing a class | The package is not exported to the consuming module, or the consuming module does not read the source module. | Check **requires** and **exports**; opens does not resolve source code access. |
| Framework on classpath still fails when the application is modular | The framework belongs to the unnamed module and the package is not opened to ALL-UNNAMED. | Consider **--add-opens module/package=ALL-UNNAMED** or move the framework to a named module. |
| Opened this package, but the framework still fails on another package | The framework is accessing a different package that has not been opened. | Identify the exact package from the error message and open only the required scope. |
| Works in IDE, fails in production | The IDE has different VM options or module access configuration from production. | Synchronize runtime arguments and module descriptors across environments. |

When troubleshooting errors, read the full exception message. JPMS messages usually name the source module, package, and caller module, helping identify which directive to examine. Avoid adding blanket **--add-opens** for every package, as that obscures the actual access design and weakens encapsulation.

## 10. Designing access permissions based on need

Some typical choices:

| Need | Appropriate directive |
|---|---|
| Expose a public API for other modules to import and call public methods | **exports package.name** |
| Expose an API only to a few known modules | **exports package.name to target.module** |
| Allow frameworks deep access to private fields/constructors at runtime | **opens package.name** |
| Allow only a specific framework/module to perform deep reflection | **opens package.name to framework.module** |
| Temporarily open a package for a framework running on the classpath | Runtime option **--add-opens module/package=ALL-UNNAMED** |
| Migrating a legacy application needing deep reflection across many packages | Consider **open module**, then narrow permissions per package when possible |

For a domain module, a descriptor might look like this:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin.host;
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

The public API is exported to all modules reading domain; the SPI is exported only to the plugin host; entities are opened only to the ORM. Other packages remain sealed. This is how to use the module descriptor to clearly express boundaries between APIs, extension points, and internal data needing reflection.

## 11. Checklist for choosing opens vs. exports

Before modifying **module-info.java**, determine:

- Does the consuming module need to import classes and call the public API in Java source code? If yes, check **exports**.
- Does the framework need to access private fields, constructors, or methods via reflection? If yes, check **opens**.
- Should access apply to all modules or only a single framework/adapter? Prefer qualified directives when the target module is clearly known.
- Does the package really need to be opened completely, or only a specific entity/configuration package?
- Is the caller a named module or the unnamed module? The unnamed module case may require **ALL-UNNAMED** in runtime options.
- Does the actual runtime environment have the same VM options and module path as the development environment?
- Does the directive accidentally expose internal packages or grant broader reflection permissions than needed?

**exports** and **opens** both serve module boundaries, but they do not replace each other. Export a package to expose an API; open a package to allow deep reflection at runtime. Grant only the exact permissions that the consuming module or framework actually needs in order to preserve encapsulation, clarify the API contract, and reduce access errors when the application runs on the module path.