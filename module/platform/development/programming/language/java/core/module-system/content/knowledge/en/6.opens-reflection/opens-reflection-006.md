# Frameworks need opens to bind, proxy, or serialize

The Java Platform Module System (JPMS) creates access boundaries between modules. A class can be public, yet a framework is still not permitted to read or modify private fields of that class using deep reflection. This is why modular applications sometimes encounter errors when frameworks perform data binding, dependency injection, proxy creation, or serialization.

The **opens** directive in module-info.java allows a specific module to perform deep reflection on a package at runtime. When scoped appropriately, the application preserves its API boundaries while the framework can access the internal members it needs.

## 1. Why do frameworks need opens?

Many frameworks work by inspecting class structure at runtime. Instead of calling only the public methods that application code calls directly, they may need to:

- Read metadata of fields, methods, constructors, and annotations.
- Instantiate objects using constructors that application code does not call directly.
- Assign values to fields or invoke setters when binding data.
- Read private fields to serialize objects into JSON or another format.
- Reconstruct objects from serialized data.
- Generate proxies or helper classes based on metadata of the original class.

Example of an entity:

~~~java
package com.example.customer.model;

public class Customer {
    private long id;
    private String name;

    protected Customer() {
    }

    public String getName() {
        return name;
    }
}
~~~

Business code can use public getters. However, an ORM or data binding library may want to invoke the non-public constructor and assign private fields directly. The fact that a framework can see the Customer class does not mean it is allowed to perform all reflection operations on the class's members.

If the package resides in a named module and has not been opened, the framework may encounter java.lang.reflect.InaccessibleObjectException when attempting deep access.

## 2. exports and opens do two different jobs

This is the most important distinction when configuring JPMS:

| Directive | Purpose | Usage example |
| --- | --- | --- |
| **exports** | Allows other modules to access the public API of a package in ordinary Java code. | Application imports CustomerService. |
| **opens** | Allows deep reflection into a package at runtime, including non-public members according to reflection rules. | ORM reads private fields or serializer accesses constructors. |

Example module descriptor:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.model to com.example.orm;
}
~~~

Other modules can use the public API in com.example.customer.api. Specifically, the com.example.orm module is permitted to perform deep reflection on com.example.customer.model.

Declaring opens does not make a package an API that can be arbitrarily imported. Conversely, exports does not automatically grant deep reflection permission into private fields. A package can be both exported and opened if the design genuinely requires both capabilities.

## 3. How to declare opens in module-info.java

### 3.1. Opening a package to all modules

~~~java
module com.example.customer {
    opens com.example.customer.model;
}
~~~

This is unqualified opens. Any other module can perform deep reflection on the model package at runtime.

This approach is simple, but its scope is broad. If only one framework needs access, use qualified opens to limit permissions.

### 3.2. Opening only to one framework

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.orm;
}
~~~

The com.example.orm module is permitted deep reflection on the model package. Other modules are not granted permission merely because they read the customer module.

Multiple packages can be opened to the same framework:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.orm;
    opens com.example.customer.persistence to com.example.orm;
}
~~~

Or one package can be opened to multiple frameworks:

~~~java
module com.example.customer {
    opens com.example.customer.model to
        com.example.orm,
        com.example.json;
}
~~~

Use the exact module name of the framework. Artifact names or JAR file names are not always identical to the module name. You can verify this with jar --describe-module --file path/to/framework.jar.

### 3.3. Opening the entire module

~~~java
open module com.example.customer {
    exports com.example.customer.api;
    requires com.example.validation;
}
~~~

open module opens all packages of the module for deep reflection at runtime. This is a broad option and is usually suitable only when a framework needs reflection across many packages that cannot be clearly enumerated individually.

If only the ORM needs access to the model package, opening that individual package is easier to control than opening the entire module.

## 4. Data binding: frameworks map data onto objects

Data binding converts external data into Java objects or converts objects into data structures. Frameworks can use constructors, setters, getters, fields, and annotations to perform mapping.

Example JSON request:

~~~json
{
  "id": 42,
  "name": "An"
}
~~~

Target object:

~~~java
package com.example.customer.model;

public class Customer {
    private long id;
    private String name;

    protected Customer() {
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

If the framework only calls public getters/setters, it may not need deep reflection into private fields. However, if the framework uses field access or needs to call a non-public constructor, the package may need to be opened.

Example module descriptor for a mapper module:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.mapper;
}
~~~

This configuration allows mapper to deeply access the model package. If mapper needs to import another public API of customer, it must still declare requires and the API package must be exported appropriately.

Do not open packages based on guesswork. Check the actual error or framework documentation to know which package and module name need to be opened.

## 5. Serialization: reading objects and reconstructing objects

Serialization often needs to read object state to produce JSON, XML, or another format. Deserialization does the reverse: instantiating objects and assigning data to properties.

A serializer can use public getters, but some configurations or libraries use reflection to access private fields. If the package resides in a named module, the serializer needs to be granted deep reflection permission.

Example with an application module:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.json;
}
~~~

The name com.example.json is only an illustrative name. When using a real JSON library, verify the module name of the exact version being run.

If the JSON library sits on the classpath, it belongs to the unnamed module. A module descriptor cannot write the name of an unnamed module in qualified opens. In that case, you can configure the JVM using --add-opens with the target ALL-UNNAMED:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=ALL-UNNAMED ...
~~~

The flag above opens the model package of the customer module for deep reflection from classes belonging to the unnamed module in that runtime.

If the framework has a named module, restrict the target to the framework's module name instead of using ALL-UNNAMED.

## 6. Proxies and dependency injection

Dependency injection or AOP frameworks can generate proxies to add behaviors such as transactions, logging, caching, lazy loading, or permission checks.

There are two common ways to implement proxies:

- **JDK dynamic proxy:** creates a proxy object based on an interface.
- **Subclass/bytecode proxy:** creates a subclass or supporting bytecode class based on the class to be proxied.

The required access permissions depend on how the framework creates proxies, the visibility of the interface/class, the package containing the type, and the framework's module. opens may be required when the framework must inspect or access non-public members via reflection. However, opens does not automatically solve every proxy creation error: reading types, subclassing classes, accessing constructors, or defining proxy classes are also subject to readability, exports, and Java access rules.

Example of a module containing a service:

~~~java
package com.example.orders.internal;

public class OrderServiceImpl {
    public void submit() {
        // Process the order.
    }
}
~~~

If an AOP framework needs deep reflection on the implementation package:

~~~java
module com.example.orders {
    opens com.example.orders.internal to com.example.aop;
}
~~~

If the framework needs to access a public interface from another module, the package containing that interface must also be exported and the framework module must read the module owning the interface.

When encountering proxy errors, read the exception to distinguish:

- InaccessibleObjectException: usually related to deep reflection; check opens.
- IllegalAccessError or package/type not visible error: check requires, exports, and type accessibility.
- Proxy class definition or constructor access error: check proxy mechanism, visibility, package, and module layer; do not assume merely adding opens is enough.

## 7. Is the framework on the module path or classpath?

This is the detail that determines how opening permission is declared.

| Framework location | Module identity | How to open the package |
| --- | --- | --- |
| JAR with module descriptor on module path | Named module | opens package to framework.module; |
| Legacy JAR recognized as an automatic module on module path | Automatic module with a name | Can use the verified module name in qualified opens. |
| JAR on classpath | Unnamed module | Use --add-opens module/package=ALL-UNNAMED if deep reflection is needed. |

Example when the framework is a named module:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.fasterxml.jackson.databind;
}
~~~

The name above is only an illustrative example of a verified module name. Verify the exact module name in the actual artifact, because library versions or packaging can affect module names.

If the framework is on the classpath:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=ALL-UNNAMED -jar app.jar
~~~

ALL-UNNAMED applies to unnamed modules in that corresponding runtime. It is broader than qualified opens to a named module, so it should only be used when the framework actually runs from the classpath.

## 8. How to find the package and module name to open

When encountering a reflection error, follow these steps:

1. Read the full exception and find the line stating the source module name, the closed package, and the target module.
2. Determine whether the package belongs to an application module or a third-party library.
3. Determine whether the framework runs on the module path or classpath.
4. If the framework has its own JAR, inspect the module name with jar --describe-module.
5. Open the right package to the right framework in module-info.java or configure --add-opens when needed.
6. Rerun the tests or actual launch command to confirm reflection permissions are sufficient.

Example message:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private java.lang.String
com.example.customer.model.Customer.name accessible:
module com.example.customer does not "opens
com.example.customer.model" to module com.example.mapper
~~~

This message already indicates three facts: the source package is com.example.customer.model, the owning module is com.example.customer, and the target module is com.example.mapper.

Fix in the descriptor:

~~~java
module com.example.customer {
    opens com.example.customer.model to com.example.mapper;
}
~~~

If the error comes from a framework on the classpath, use ALL-UNNAMED in the JVM argument instead of writing an assumed name for the unnamed module.

## 9. Opening packages in module-info.java or using --add-opens?

The two approaches have slightly different purposes:

| Approach | Suitable when | Characteristics |
| --- | --- | --- |
| opens in module-info.java | You maintain the module and know which framework needs reflection | Opening permission is recorded in the module descriptor, easy to review alongside source code. |
| --add-opens | Need to integrate an unmodifiable library, test quickly, or adjust deployment configuration | Opening permission is granted at runtime via JVM arguments. |

Example argument:

~~~bash
java --add-opens com.example.customer/com.example.customer.model=com.example.mapper -m com.example.app/com.example.app.Main
~~~

Do not add --add-opens for every package just to make errors disappear. Keep the scope small and document which framework needs that permission, so the configuration can be reviewed when upgrading dependencies.

## 10. Common misconceptions

**If a package has public classes, frameworks can always access them:** Incorrect. JPMS also controls whether the package is exported or opened.

**Adding exports will fix all reflection errors:** Incorrect. exports is for normal API access; deep reflection into non-public members requires opens.

**opens makes a package importable from source code:** Incorrect. opens does not replace exports.

**Every framework has a module name:** Incorrect. Frameworks running on the classpath belong to the unnamed module; you cannot write that name as a target module in qualified opens.

**Adding opens is enough for proxies to work:** Not always. Proxy mechanisms also depend on interface/class visibility, constructors, packages, readability, and module layers.

**Opening the entire module is always safest and most convenient:** A broad opening scope weakens encapsulation. Open only the right packages and frameworks that need access.

## 11. Example descriptor for an application using ORM and serializer

Suppose an application has a public API and an internal model that an ORM and a JSON mapper need deep access to:

~~~java
module com.example.customer {
    requires java.sql;

    exports com.example.customer.api;

    opens com.example.customer.model to
        com.example.orm,
        com.example.json;
}
~~~

Meaning:

- The customer module reads java.sql.
- Other modules can use the public API in the api package if they have an appropriate requires relationship.
- The ORM and JSON mapper are granted deep reflection on the model package.
- Other internal packages retain their encapsulation boundaries.

If the JSON mapper actually runs on the classpath, remove that illustrative name from qualified opens and configure --add-opens ...=ALL-UNNAMED according to the runtime. If the framework uses a named module, replace it with the verified actual module name.

## 12. Checklist when integrating frameworks with JPMS

- Determine whether the framework needs to call public APIs or needs deep reflection.
- Identify the packages containing models/entities/DTOs that the framework accesses.
- Determine whether the framework is a named module, automatic module, or unnamed module.
- Use requires and exports for normal dependencies/APIs.
- Use opens or --add-opens for deep reflection.
- Limit opening permissions to the packages and frameworks that genuinely need them.
- Check proxy errors separately because opens does not replace all type and package access rules.
- Run binding, proxy, and serialization tests on the exact module path or classpath of the deployment environment.

JPMS does not forbid frameworks from working with objects that have private fields. It requires the module owning the package to explicitly declare which packages are open for reflection. When configured properly, frameworks can still bind, create proxies, or serialize data while other internal packages remain encapsulated.