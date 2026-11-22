# Strong encapsulation and InaccessibleObjectException

**Strong encapsulation** is the JPMS mechanism that restricts access to packages of a named module. A module only exposes an API to other modules through exported packages; deep reflection into non-public members is only permitted when the package is opened appropriately. This mechanism helps modules control implementation boundaries and reduce dependency on internal details.

When a framework or library uses reflection to access an unopened package, the application can encounter `java.lang.reflect.InaccessibleObjectException`. This is a common error when migrating legacy applications to Java with the module system or when upgrading the JDK while a library still attempts to access internal members.

This lesson focuses on identifying the cause, distinguishing `exports` from `opens`, choosing an appropriate fix, and verifying configuration on JDK 21.

## 1. What does strong encapsulation protect?

Before JPMS, many applications relied on the classpath and reflection to access classes or members that were not designed as public APIs. A framework could call `setAccessible(true)` on a private field, or access an internal package of another library. This approach often depended on implementation details and could break when the library changed.

JPMS brings module boundaries into the JVM's access model. For a named module:

- Unexported packages cannot be used by other modules as ordinary APIs.
- Unopened packages do not allow other modules to perform deep reflection into non-public members.
- Java access modifiers such as `public`, `protected`, package-private, and `private` remain in effect inside module boundaries.
- A module can decide which packages are public APIs and which packages are opened only to specific frameworks or integration modules.

Strong encapsulation helps prevent applications from depending on the internals of other modules, especially JDK internals. When the JDK changes its implementation, applications built on supported APIs are more stable than applications accessing internal classes or fields.

### Strong encapsulation across JDK versions

JPMS was introduced in JDK 9. The initial transition included several compatibility mechanisms so legacy applications could continue running. JDK 16 applied broader default strong encapsulation to JDK internal APIs; JDK 17 completed the strong encapsulation of JDK internals under JEP 403.

Since JDK 17, the `--illegal-access` option no longer restores the broad open access of early JPMS JDK releases. Applications must handle each specific package using supported APIs, `opens` declarations, or clearly scoped `--add-opens` options.

## 2. When does InaccessibleObjectException appear?

`InaccessibleObjectException` is an unchecked exception in the `java.lang.reflect` package. It can appear when code calls `AccessibleObject.setAccessible(true)` but the JVM does not allow bypassing access checks for that reflection object.

For example, a library has a domain class:

~~~java
package com.acme.domain.model;

public class Customer {
    private String name = "An";
}
~~~

A framework in another module wants to read the private field using reflection:

~~~java
import java.lang.reflect.Field;

Field field = Customer.class.getDeclaredField("name");
field.setAccessible(true);
Object value = field.get(customer);
~~~

If the package `com.acme.domain.model` resides in a named module and has not been opened to the module containing the framework, the `setAccessible(true)` call can throw `InaccessibleObjectException`.

This error does not mean the private field somehow became public. Reflection is asking the JVM to allow bypassing normal access checks; JPMS rejects that request because the package has not been opened to the caller.

### setAccessible and trySetAccessible

Two APIs are commonly used to control the accessibility of reflection objects:

- `setAccessible(true)` attempts to enable bypassed access. If the module system does not permit it, the method can throw `InaccessibleObjectException`.
- `trySetAccessible()` attempts to enable access and returns `true` if successful, `false` if it cannot be enabled. This approach is suitable when a library wants to handle unopened cases without using exceptions for primary control flow.

Example:

~~~java
Field field = Customer.class.getDeclaredField("name");

if (field.trySetAccessible()) {
    Object value = field.get(customer);
    System.out.println(value);
} else {
    System.out.println("Package is not open for deep reflection");
}
~~~

`trySetAccessible()` does not open the package itself and does not change the module descriptor. It only indicates whether the current caller is permitted to enable access.

## 3. Distinguishing exports from opens

Both `exports` and `opens` are declared at the package level in the module descriptor, yet they address two different types of access.

| Directive | Purpose | Usage scenario |
|---|---|---|
| `exports package.name` | Exposes the package's public API to other modules | Source code in another module imports and calls public types |
| `opens package.name` | Allows deep reflection into the package at runtime | Framework needs to read/write private fields or invoke non-public members |
| `exports package.name to target.module` | Exposes the API only to the specified module | Limits the set of modules allowed to use the API |
| `opens package.name to target.module` | Opens reflection only to the specified module | Limits the frameworks/modules allowed deep access |

An exported package is not by default opened for deep reflection. Conversely, a package opened for reflection does not by default become an API that other modules can import at compile time.

Example domain module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

In this configuration:

- Any module that reads `com.acme.domain` can access public types in `com.acme.domain.api`.
- Only the `com.acme.json` module is permitted deep reflection into `com.acme.domain.model`.
- Other packages of the domain module remain encapsulated by default.

If a framework runs on the classpath, the reflection caller belongs to the unnamed module. When opening a package to classpath libraries is needed, you can use the launcher option `--add-opens` with target `ALL-UNNAMED`.

## 4. Why does a package need to be opened?

Some frameworks operate by inspecting class structures and accessing members that application code does not call directly. Common cases:

- **Serialization/deserialization:** frameworks need to read or set non-public fields to map objects to JSON/XML.
- **Dependency injection:** containers need to find annotated constructors, fields, or methods and may need to access non-public members.
- **ORM/persistence:** frameworks map data columns to fields or invoke constructors according to their conventions.
- **Testing/mock:** testing tools need to modify internal state or access private members to support certain testing techniques.
- **Reflection-based mapping:** libraries analyze class metadata and invoke accessors or members according to configuration.

Not every reflection operation requires `opens`. Accessing public APIs through an already-exported package may not require deep reflection. The need to open a package arises when a framework must bypass normal access checks to reach non-public members.

Identify the exact package and caller module from the stack trace. An error caused by a framework accessing `java.base/java.lang` is different from an error caused by a framework accessing an application's domain package; the resolution and impact are also different.

## 5. Reading the stack trace to find the package to open

Error messages usually take the form:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

The message provides three key pieces of information:

1. **Source module:** in the example, `java.base`, the module containing the class/field the framework wants to access.
2. **Source package:** `java.lang` is the package that needs to be opened.
3. **Target module:** `unnamed module` is the caller's module, typically a library running on the classpath.

If the error originates from an application module, the message may indicate the application module name and domain package, for example:

~~~text
module com.acme.domain does not "opens com.acme.domain.model"
to module com.acme.json
~~~

From this information, determine:

- Which module owns the class/field being accessed.
- Which package contains that class.
- Which module performs the reflection.
- Whether the framework has a JPMS-compatible version or another integration approach.

Do not rush to open packages based on the last class name in the stack trace. The message line mentioning the module and package tells you the exact JPMS boundary blocking access.

## 6. Preferred ways to resolve

### Update the framework or library

First, check the framework version. Older versions may rely on reflection over JDK internal implementations or access packages that newer versions have changed. An upgraded version may have switched to supported APIs, adjusted its reflection strategy, or added appropriate module configuration.

This is usually the most sustainable fix because it does not widen the module's access permissions.

### Use supported public APIs

If the application is accessing a JDK internal class, look for a public API alternative. For example, instead of operating directly on an implementation class or internal field, use the official JDK API.

You should not depend on internal class names, private JDK fields, or unexported packages. These details can change between Java versions.

### Open the right package in the module descriptor

If the framework genuinely needs deep reflection into a package owned by the application, declare qualified opens:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

The `com.acme.json` module must be the actual caller of the reflection. Only open the package needed by that framework. Other packages retain encapsulation.

If multiple frameworks need deep reflection into the same package, multiple target modules can be listed:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to
        com.acme.json,
        com.acme.persistence;
}
~~~

### Use open module when there is a broad need

You can declare:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

An open module opens all of its packages for deep reflection at runtime. This approach can suit an application/framework designed around widespread reflection, but it reduces the encapsulation of the entire module.

If only a few packages need to be accessed by a framework, prefer `opens package.name to module.name` for a clearer scope. Do not declare individual `opens` directives inside an `open module`.

## 7. Using --add-opens when adjustments are needed at launch

When you cannot modify a library's module descriptor or are migrating a system, the Java launcher provides the `--add-opens` option:

~~~text
--add-opens source.module/package=target.module
~~~

Example opening package `java.lang` of `java.base` to all unnamed modules:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

If the framework is a named module, specify the target module name instead of `ALL-UNNAMED`:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=com.acme.json \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

In this command:

- `com.acme.domain` is the module containing the package to open.
- `com.acme.domain.model` is the package to allow deep reflection on.
- `com.acme.json` is the module performing the reflection.

`ALL-UNNAMED` is a special target name of the launcher option, meaning it applies to all unnamed modules. It is commonly used when frameworks run on the classpath. This is not a valid module name to write in an `opens ... to ...` directive of `module-info.java`.

The `--add-opens` option only takes effect for the process launched with that option. It does not edit JAR files, does not change `module-info.class`, and does not automatically apply to other Java processes such as test workers, plugin processes, or separately launched services.

In Gradle, JVM arguments must be placed on the exact task/process running the application or tests. Adding the option only to the application run command does not ensure the test worker also receives that configuration.

## 8. Distinguishing --add-opens from --add-exports

Two options are often misused:

- `--add-exports` allows accessing public types in an unexported package to the target module. It supports public API access across module boundaries.
- `--add-opens` opens a package for deep reflection into non-public members at runtime.

Example:

~~~bash
# Allow accessing public types in the package
java --add-exports java.base/sun.security.util=ALL-UNNAMED ...

# Allow deep reflection into the package
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

If the error states that a package is not exported when compiling or linking code, consider `exports` or `--add-exports`. If the error occurs when a framework calls `setAccessible(true)` on a non-public field/constructor/method, consider `opens` or `--add-opens`.

Do not use `--add-exports` as a substitute for deep reflection errors. Exporting a package does not mean granting deep access to private members.

## 9. Why is --illegal-access no longer a solution?

In early JDK releases with JPMS, the `--illegal-access` option provided compatibility for certain reflective accesses to JDK internal packages. This mechanism was transitioned across versions and strong encapsulation became the default in JDK 16; JDK 17 completed the strong encapsulation of JDK internals.

On JDK 17 and later, `--illegal-access` no longer restores the old broad access mode. Adding this option is not an appropriate fix for `InaccessibleObjectException`. Identify the target module/package and use public APIs or specifically scoped `--add-opens` when genuinely needed.

## 10. Step-by-step diagnostic process

When encountering `InaccessibleObjectException`, perform these steps in order:

1. **Read the full message:** record the source module, source package, and target module stated in the exception.
2. **Identify the caller:** find the framework/library making the reflection call in the stack trace; check whether it is a named module or the unnamed module.
3. **Determine the actual need:** does the framework need to access private members or only public APIs?
4. **Inspect the descriptor:** use `jar --describe-module --file ...` or read `module-info.java` to see whether the package is exported/opened.
5. **Prefer updating or switching APIs:** remove dependencies on internal implementations if supported APIs exist.
6. **Open the package narrowly:** add qualified `opens` to the module descriptor or pass `--add-opens` to the right JVM process.
7. **Rerun in the actual environment:** verify that the application, test worker, Gradle task, or separate processes all receive the required configuration.
8. **Narrow configuration after transition:** once the framework is upgraded and no longer needs the package opened, remove temporary options.

You can use `jdeps` to scan for dependencies on JDK internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

This command helps detect certain references to JDK internal APIs in bytecode. It does not replace reading the stack trace because reflection errors can arise from frameworks or dynamically loaded dependencies.

## 11. Pre-release checklist

- [ ] Identify the exact blocked module and package from the exception.
- [ ] Determine whether the caller module is a named module or the unnamed module.
- [ ] Check whether the framework has a version compatible with the JDK/module system in use.
- [ ] Prefer public APIs over accessing internal implementations.
- [ ] If reflection is needed, open only the necessary packages.
- [ ] Use qualified `opens` to specific target modules when possible.
- [ ] Place `--add-opens` on the right JVM process, including test workers if needed.
- [ ] Do not confuse `--add-exports` with `--add-opens`.
- [ ] Do not rely on `--illegal-access` on modern JDKs.
- [ ] Document the reason and scope for every opened package so it can be narrowed later.

## 12. Key takeaways

Strong encapsulation is the boundary protecting packages of a named module. `InaccessibleObjectException` typically occurs when reflection code attempts deep access into a package not yet opened to the caller module. `public` and `exports` address ordinary API access; `opens` and `--add-opens` address deep reflection needs.

Start from the module/package/caller in the error message, check the framework's needs, and prefer updating the library or using supported APIs. Open only the exact package and exact target module when reflection is genuinely necessary. A clearly scoped fix lets the application keep using frameworks while preserving most of JPMS's encapsulation benefits.