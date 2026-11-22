# InaccessibleObjectException During Deep Reflection

## 1. What Is InaccessibleObjectException?

**InaccessibleObjectException** is an unchecked exception in Java Reflection that occurs when a program attempts to grant deep access to a member that JPMS does not allow accessing. The error commonly occurs when a framework calls **setAccessible(true)** on a private field, method, or constructor belonging to a package of a named module that has not been opened to the calling module.

Starting in Java 9, the Java Platform Module System (JPMS) added encapsulation boundaries between modules. A package may exist and a class may be loadable, but that does not mean other modules are allowed to access every member inside the package.

For example, a framework may discover an entity class and read its metadata, but when it tries to access a private field to map data, the JVM rejects the operation. In that case, finding the class does not mean deep reflection is permitted.

The error message typically has the form:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module ... does not "opens ..." to ...
~~~

The message states the module owning the package, the blocked package, and the module requesting access. This is important information for determining which package needs to be opened and to whom.

## 2. Why Does JPMS Block Deep Reflection?

Before JPMS, many libraries relied on reflection to access private fields, constructors, or internal methods. Some frameworks use this technique for dependency injection, ORM, serialization, proxies, or mapping.

JPMS adds two important encapsulation concepts:

- **exports** allows other modules to access public types in a package.
- **opens** allows other modules to use deep reflection on members in a package, including non-public members.

Therefore, declaring **exports** does not automatically allow a framework to call **setAccessible(true)** on a private field. If a framework needs deep access, the package must be opened using **opens** or an appropriate runtime option.

The JDK also applies strong encapsulation to its internal packages. Packages such as **sun.* ** or other internal packages are not public APIs guaranteed for compatibility. An older framework might work on an earlier JDK but fail on a newer JDK because it relies on internal access.

Starting in JDK 17, strong encapsulation is applied by default to internal JDK packages. The old **--illegal-access** option is no longer a way to reopen internal packages wholesale. You must update the library or open the exact package if there is a specific implementation reason.

## 3. Distinguishing Class Discovery, Public Access, and Deep Reflection

When investigating reflection errors, separate three steps:

1. **Discovery:** the framework finds classes or resources via package scanning, annotations, ServiceLoader, or configuration.
2. **Loading:** a classloader or module layer successfully loads the class.
3. **Access:** the framework is permitted to read or modify the members it needs.

For example, a module might export an API package so a framework can invoke public methods. The framework may still fail to access private fields in the same package if the package has not been opened to it.

### Public access through an exported package

Module containing the API:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

A framework can use public types in the exported package if the framework module reads the model module:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

This is regular Java API access. There is no need to open the package for deep reflection if the framework only calls permitted public methods.

### Private access via reflection

Suppose a class has a private field:

~~~java
package com.example.model.api;

public class Customer {
    private String email = "customer@example.com";

    public String email() {
        return email;
    }
}
~~~

The framework wants to access the private field:

~~~java
Field field = Customer.class.getDeclaredField("email");
field.setAccessible(true);

String value = (String) field.get(customer);
~~~

If the **com.example.model.api** package is only exported and not opened to the framework module, the **setAccessible(true)** call can throw **InaccessibleObjectException**. Public access permission and deep reflection permission are two separate permissions.

## 4. Reading the Error Message Correctly

A typical message:

~~~text
Unable to make field private ... accessible:
module com.example.model does not "opens com.example.model.api"
to module com.example.framework
~~~

You can read the message in parts:

- **com.example.model** is the module owning the class and package.
- **com.example.model.api** is the package being accessed deeply.
- **com.example.framework** is the module invoking reflection and needing permission.
- The **opens** keyword indicates the operation requires deep reflection permission.

If the message states the package is not open to **ALL-UNNAMED**, the caller belongs to the unnamed module, usually a library running from the classpath. If the message names a specific module, you must open the package to that exact named module.

Do not open an arbitrary package just because its name appears in the stack trace. Identify the class actually being accessed and the caller module recorded in the message.

## 5. Approach 1: Open the Package in module-info.java

If you own the module containing the class needing reflection, you can declare **opens** in the module descriptor.

Example:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.api
        to com.example.framework;
}
~~~

This declaration allows the **com.example.framework** module to perform deep reflection into the **com.example.model.api** package. Other modules do not receive this open permission.

If the framework needs deep reflection into a separate package, open only that package:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.internal
        to com.example.framework;
}
~~~

In this example, the public API resides in the **com.example.model.api** package, while the implementation package **com.example.model.internal** is opened selectively to the framework.

You can open a package without specifying a target module:

~~~java
module com.example.model {
    opens com.example.model.internal;
}
~~~

This form opens the package to every module for deep reflection access. Use it only when that scope is genuinely necessary.

### open module

You can declare the entire module as open:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

An **open module** opens all of the module's packages for deep reflection. This approach is appropriate when a framework needs access to many packages and opening everything is acceptable in the design. For typical applications, targeted opening using **opens package to module** is easier to control.

You cannot declare individual **opens** directives inside an **open module**; the open status already applies to all packages.

## 6. Approach 2: Use --add-opens at Launch

If you cannot modify the module descriptor, or want to test a change before committing it to source code, you can use the **--add-opens** option of the Java launcher.

Syntax:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Example opening an application module's package to a framework:

~~~bash
java \
  --add-opens com.example.model/com.example.model.api=com.example.framework \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Where:

- **com.example.model** is the module owning the package.
- **com.example.model.api** is the package to open.
- **com.example.framework** is the module permitted to perform deep reflection.

If the framework runs from the classpath, the caller belongs to an unnamed module. You can open the package to all unnamed modules using **ALL-UNNAMED**:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

This command illustrates opening the **java.lang** package in the **java.base** module to code running in the unnamed module. It commonly appears when legacy libraries require deep reflection into certain JDK classes.

If the framework is a named module, specify the exact module name instead of **ALL-UNNAMED**:

~~~bash
java \
  --add-opens java.base/java.lang=com.example.framework \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

You can open to multiple target modules using a comma-separated list:

~~~bash
java --add-opens com.example.model/com.example.model.api=com.example.framework,com.example.test
~~~

**--add-opens** is a runtime option of the Java launcher. Placing it in a **javac** command will not solve deep reflection errors when the application runs. If the application launches via a script, service, or container, add the option to the launch configuration of that exact Java process.

## 7. Distinguishing exports, opens, --add-exports, and --add-opens

These four mechanisms serve different purposes:

| Mechanism | Scope | Purpose |
|---|---|---|
| **exports package** | Module descriptor | Exposes public types in the package to other modules |
| **opens package** | Module descriptor | Allows deep reflection into the package |
| **--add-exports** | Compile/runtime command-line option | Adds access to public types in an unexported package |
| **--add-opens** | Java launcher runtime option | Opens a package for deep reflection in the current process |

For example, if source code needs to import a public type residing in an unexported package of another module, **--add-exports** can resolve the public type access error:

~~~bash
javac \
  --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
  -cp "lib/*" \
  -d out \
  src/com/example/Main.java
~~~

However, **--add-exports** does not allow deep reflection into private fields or private methods. For that case, **opens** or **--add-opens** is needed.

Conversely, **--add-opens** does not turn a package into a public API importable in source code. It only grants deep reflection permission at runtime.

If an error occurs during compilation because a module does not read another module, check **requires** or **--add-reads**. If the error is due to an unexported package, check **exports** or **--add-exports**. If the error is due to accessing private members via reflection, check **opens** or **--add-opens**.

## 8. trySetAccessible and How to Handle It in Code

Instead of assuming reflection will always succeed, a framework can use **trySetAccessible()** to check access permission:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Package is not open for deep reflection"
    );
}

String value = (String) field.get(customer);
~~~

If the module does not open the appropriate package, **trySetAccessible()** returns **false**. This is a controlled way for a framework to provide a clear message or fall back to a public API.

If calling directly:

~~~java
field.setAccessible(true);
~~~

The JVM can throw **InaccessibleObjectException** when deep access cannot be granted. Catch the error at the reflection integration layer if you need to add information about the module, package, and configuration option.

**canAccess(target)** can be used to check the current access status. For instance fields or methods, pass the target object; for static members, pass **null**.

Do not catch **InaccessibleObjectException** and silently skip every field. Skipping can cause data loss, produce incorrect mappings, or create hard-to-detect errors downstream.

## 9. Why Do Errors Often Appear on Newer JDKs?

Some libraries written before JPMS existed rely on internal JDK structures. They may access private fields of JDK classes, or use internal packages for optimization.

When running on newer JDKs:

- Internal packages may be more strongly encapsulated.
- Reflection on private members may be denied.
- An internal API that previously worked may have changed or been removed.
- Legacy compatibility options may no longer be in effect.

Starting in JDK 17, you should not rely on **--illegal-access** to restore previous internal access behavior. The sustainable fix is to upgrade the library, switch to public APIs, or open only the required package if the library vendor requires it and it is acceptable.

You can use jdeps to find some bytecode references to internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

This command helps detect static references. Class names constructed from configuration strings or dynamic reflection are not necessarily detected, so you still need to inspect stack traces and framework configuration.

## 10. Troubleshooting and Fixing Workflow

When encountering **InaccessibleObjectException**, you can follow this sequence:

1. Read the full error message to identify the source module, package, and caller module.
2. Determine whether the framework is accessing a public API or needs deep reflection into a private member.
3. Inspect the module descriptors of the module containing the class and the caller.
4. If the package belongs to a module owned by the project, add **opens package to framework.module** with the proper scope.
5. If the descriptor cannot be modified yet, try **--add-opens source.module/package=framework.module** in the launch command.
6. If the caller is on the classpath, use **ALL-UNNAMED** when needed and limit the opened packages.
7. If the package belongs to the JDK, look for a public API or upgrade the library before deciding to open a JDK package.
8. Re-run the exact Java process and test the relevant reflection features.

Once fixed, verify not only that the application starts, but also that operations actually requiring reflection succeed: entity creation, dependency injection, serialization/deserialization, proxy generation, or data mapping as applicable.

## 11. Common Configuration Mistakes

**Opening the wrong module or package**

Names in **--add-opens** must be actual module and package names. Packages use dots, not directory paths. The target module must be the framework module invoking reflection.

**Using ALL-UNNAMED for a named module framework**

**ALL-UNNAMED** applies only to unnamed modules, typically code on the classpath. If the framework is in a named module, specify the framework module name.

**Using exports to fix private reflection errors**

**exports** permits access to public types. It does not grant deep access to private fields or methods. Use **opens**.

**Adding --add-opens to javac**

This option belongs to the Java launcher at runtime. If the error occurs when the application runs, configure the actual Java process.

**Package already opened but still failing**

Check whether the package matches the package reported in the error, whether the caller module is correct, whether the launch command actually receives the option, and whether the application is running in a different module layer/process.

**Opening the entire JDK**

Broadly opening many JDK packages reduces encapsulation and increases dependence on internal implementation. Open only the exact package, for the exact caller, and only when no suitable public API solution exists.

## 12. Takeaways

- **InaccessibleObjectException** usually indicates that deep reflection is not permitted by JPMS.
- **exports** allows access to public types; **opens** allows deep reflection.
- **--add-opens** grants deep reflection permission when launching a Java process; it does not modify the module descriptor.
- **ALL-UNNAMED** is used for code in unnamed modules, typically libraries on the classpath.
- **trySetAccessible()** lets you check whether access can be opened before acting.
- Strong encapsulation of the JDK protects internal implementations; prefer public APIs and JPMS-aware libraries.
- Open only the packages truly required for the specific framework module.

When you clearly understand the module owning the package, the caller module, and the type of access the framework needs, you can resolve reflection errors with a small, well-controlled permission scope. Treat **opens** or **--add-opens** as intentional access configuration, and retest the application on the exact JDK version used in deployment.
