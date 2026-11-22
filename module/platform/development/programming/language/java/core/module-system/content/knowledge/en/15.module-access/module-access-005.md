# Reflection Access Differs from Compile-Time Access

A piece of Java code can compile successfully yet fail when using reflection. Conversely, the Reflection API can find a member's metadata without being allowed to read, write, or invoke that member. Both situations happen because Java checks access permissions at different times and under different rules.

When working with the Java Platform Module System (JPMS, since Java 9), you need to distinguish three layers of access:

1. **Compile-time access:** whether the compiler allows source code to reference a type, constructor, method, or field.
2. **Normal runtime access:** whether the JVM allows bytecode to access the member under Java and module rules.
3. **Reflective access:** whether the Reflection API is allowed to perform operations on the member; deep reflection on non-public members also depends on whether the package is open (**opens**).

## 1. Compile-Time Access Is Checked During Compilation

Compile-time access is the permission that **javac** checks from source code. It is based on the Java language's access rules:

- **public:** accessible from appropriate call sites if the enclosing type is also accessible.
- **protected:** accessible within the same package or under subclass rules.
- **package-private** (no modifier written): accessible only within the same package.
- **private:** accessible only within the declaring class and special language-defined cases such as nestmates.

With named modules, cross-module access also requires two conditions:

- The calling module must **read** the module containing the API, typically via **requires**.
- The package containing the API must be **exported** by the provider module via **exports**.

Example:

~~~java
module com.example.app {
    requires com.example.domain;
}
~~~

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

If **com.example.app** imports a **public** class in **com.example.domain.api**, both the module reads relationship and the package export must be valid. If **requires** is missing, javac may report that the module does not read the target module. If the package is not exported, the compiler may report that the package is not visible or not exported.

**opens** does not replace **exports** for source code. A package opened for reflection does not thereby become a package that can be imported and used directly in normal Java code.

## 2. Reflection Access Is Checked at Runtime

Reflection allows a program to inspect classes and members while the application is running, for example:

- **Class.forName(...)** to look up a class by name.
- **getMethod(...)**, **getDeclaredMethod(...)** to look up a method.
- **getField(...)**, **getDeclaredField(...)** to look up a field.
- **Constructor.newInstance(...)**, **Method.invoke(...)**, **Field.get(...)**, or **Field.set(...)** to operate on a member.

Key point: **finding a member does not mean being allowed to access that member**.

Example:

~~~java
Field field = User.class.getDeclaredField("passwordHash");
~~~

This statement asks the Reflection API to find the field named **passwordHash** declared directly in **User**. It does not automatically grant permission to read the private field. When **field.get(user)** is called, reflection still performs an access check.

| API | Meaning | Automatically bypasses access checks? |
| --- | --- | --- |
| **getMethod(...)** | Finds a public method, including matching inherited methods | No |
| **getDeclaredMethod(...)** | Finds a method declared directly in the class, including non-public methods | No |
| **getField(...)** | Finds a public field, including matching inherited fields | No |
| **getDeclaredField(...)** | Finds a directly declared field, including non-public fields | No |
| **Method.invoke(...)** | Invokes a method via reflection | No; still requires access permission |
| **Field.get(...) / set(...)** | Reads/writes a field via reflection | No; still requires access permission |
| **trySetAccessible()** | Attempts to enable bypassing certain language checks | Succeeds only when module conditions permit |
| **setAccessible(true)** | Requests enabling access-check suppression | May be rejected |

The Reflection API can provide metadata about a member without granting permission to perform operations on that member. Therefore, do not treat **getDeclaredField** or **getDeclaredMethod** succeeding as proof that the package is open.

## 3. Distinguishing exports and opens

In JPMS, **exports** and **opens** serve two distinct purposes.

| Declaration | What does it allow? | When is it used? |
| --- | --- | --- |
| **exports p;** | Other modules use public types and members of package p under Java access rules | Compile time and runtime |
| **exports p to m;** | Only module m can use the public API of package p | Compile time and runtime |
| **opens p;** | Allows deep reflection on types/members of package p from other modules | Runtime |
| **opens p to m;** | Only module m can perform deep reflection on package p | Runtime |
| **open module x { ... }** | Opens all packages of the module for deep reflection from other modules | Runtime |

Example of a domain module exposing an API and opening a model package only to one framework:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.mapper;
}
~~~

In this configuration:

- Code in other modules can import **public** classes in **com.example.domain.api** if they have an appropriate module reads relationship.
- The framework in **com.example.mapper** can perform deep reflection on **com.example.domain.model**.
- Package **com.example.domain.model** does not automatically become directly importable just because it has **opens**.
- Modules not listed in the qualified **opens** do not receive that deep reflection permission.

If you declare **open module com.example.domain { ... }**, all packages of the module are opened for reflection. An open module can still use **exports** to expose APIs for normal access; **open** does not turn every package into an importable public API. In an open module, do not declare separate **opens** directives because all packages are already open.

**Rule of thumb:** **exports** is for public API access; **opens** is for deep reflection. A package may need both if it is both a directly called API and contains internal members that a framework needs to read via reflection.

## 4. Java Access Modifiers and Module Access Are Two Checking Layers

Access modifiers and module declarations complement each other. **public** does not mean every module can access it; **private** also cannot be bypassed arbitrarily just by using reflection.

Example:

~~~java
package com.example.domain.model;

public class User {
    public String displayName = "An";
    private String passwordHash = "hash-value";
}
~~~

Suppose package **com.example.domain.model** is neither exported nor opened to the calling module.

- **displayName** has the **public** modifier, yet another module still cannot access it as a normal public API if the package is not exported.
- **passwordHash** has the **private** modifier; direct access from an external class is invalid under Java rules anyway.
- **getDeclaredField("passwordHash")** can retrieve the field's metadata, but does not grant permission to read the field.
- **setAccessible(true)** can be rejected because the package is not open to the calling module.

If the package is exported, external code can use valid public members, yet that does **not** automatically permit reflection to access private fields. If the package is opened, deep reflection may be allowed, yet normal Java code still cannot import that package if it is not exported.

## 5. Example: Public Reflection and Deep Reflection

Suppose there are two modules:

~~~text
com.example.domain/
  module-info.java
  com/example/domain/api/UserView.java
  com/example/domain/model/UserRecord.java

com.example.framework/
  module-info.java
  com/example/framework/Inspector.java
~~~

Domain module descriptor:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.framework;
}
~~~

Public API class:

~~~java
package com.example.domain.api;

public class UserView {
    public String label() {
        return "User";
    }
}
~~~

Model class with a private field:

~~~java
package com.example.domain.model;

public class UserRecord {
    private String internalId = "U-100";

    public String getInternalId() {
        return internalId;
    }
}
~~~

Framework module:

~~~java
module com.example.framework {
    requires com.example.domain;
}
~~~

The following code can call the exported public API:

~~~java
UserView view = new UserView();
System.out.println(view.label());
~~~

Whereas if the framework needs to read **internalId** via reflection:

~~~java
package com.example.framework;

import com.example.domain.model.UserRecord;
import java.lang.reflect.Field;

public class Inspector {
    public static void main(String[] args) throws Exception {
        UserRecord user = new UserRecord();

        Field field = UserRecord.class.getDeclaredField("internalId");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Deep reflection on internalId is not allowed"
            );
        }

        Object value = field.get(user);
        System.out.println(value);
    }
}
~~~

This example illustrates deep reflection permission granted by **opens com.example.domain.model to com.example.framework**. If the **opens** line is removed, looking up the field may still succeed, but **trySetAccessible()** cannot enable private access in that closed package; reading the field will not be allowed.

If you only declare:

~~~java
exports com.example.domain.model;
~~~

the framework can use public members in the package under normal rules, yet it still cannot read private fields via deep reflection.

## 6. Using canAccess, trySetAccessible, and setAccessible Properly

Since Java 9, **AccessibleObject** provides helpful APIs for checking and requesting access.

### canAccess(Object obj)

Used to check whether the current caller can access the reflected member with the given receiver. For instance members, pass the corresponding receiver object; for static members or constructors, pass **null**.

~~~java
Field field = UserRecord.class.getDeclaredField("internalId");
UserRecord user = new UserRecord();

if (field.canAccess(user)) {
    System.out.println(field.get(user));
}
~~~

**canAccess** does not open a package or change module configuration. It only checks current accessibility.

### trySetAccessible()

Used when an application needs to attempt enabling access-check suppression under Java rules:

~~~java
Field field = UserRecord.class.getDeclaredField("internalId");

if (field.trySetAccessible()) {
    Object value = field.get(user);
    System.out.println(value);
} else {
    System.out.println("Module does not yet allow deep reflection");
}
~~~

If the module does not allow opening the package, **trySetAccessible()** returns **false**. This approach fits when the application wants to handle lack of permission without letting **InaccessibleObjectException** be thrown immediately at the call site.

### setAccessible(true)

~~~java
field.setAccessible(true);
Object value = field.get(user);
~~~

This call requests enabling access-check bypass. If JPMS conditions disallow it, the JVM can throw **InaccessibleObjectException**. Therefore, do not assume **setAccessible(true)** will always succeed.

**setAccessible(true)** cannot arbitrarily open any member of any module. It does not replace module descriptors or runtime configuration. Use deep reflection only when there is a clear need and the target module intentionally permits it.

## 7. --add-exports vs. --add-opens

These two flags are often misused when troubleshooting reflection errors.

**--add-exports** adds package export permission to a target module. It supports accessing public types/members under normal rules. It may be needed at compile time and runtime:

~~~bash
# Compile time
javac --add-exports com.example.domain/com.example.domain.internal=com.example.app ...

# Runtime
java --add-exports com.example.domain/com.example.domain.internal=com.example.app ...
~~~

**--add-opens** opens a package for deep reflection at runtime:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.framework ...
~~~

If the caller belongs to an unnamed module (such as an application or framework running on the classpath), **ALL-UNNAMED** can be used:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;libs/*" com.example.Main
~~~

This example uses the Windows classpath separator. On Linux/macOS, replace **;** with **:**.

Key points to remember:

- **--add-exports** does not open private members for deep reflection.
- **--add-opens** does not make a package directly importable in source code.
- **--add-opens** is a runtime option; do not use it to fix compile-time access errors.
- **ALL-UNNAMED** targets unnamed modules, typically code on the classpath.
- If you own the source module, declaring **exports** or **opens** in **module-info.java** is usually easier to maintain than relying on external launch flags.

Do not add both flags out of habit. Read the error message to determine whether public API access or deep reflection permission is missing.

## 8. Reflection and Method Handles

Reflection is not the only way to operate on members dynamically. Java also has Method Handles via **java.lang.invoke**.

**MethodHandles.Lookup** has its own access levels. When you need a lookup with private access in a class belonging to another module, **MethodHandles.privateLookupIn(...)** requires appropriate module conditions, including the caller module reading the target module and the target package being open to the caller.

Conceptual example:

~~~java
MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
    UserRecord.class,
    MethodHandles.lookup()
);
~~~

If the package is not open or module relationships do not satisfy the requirements, this operation fails with the corresponding access error. **privateLookupIn** is not a way to bypass JPMS; it obeys module rules and lookup permissions.

When you only need to call a public API, use normal Java calls or a method handle with appropriate permissions. Only use deep reflection or private lookup for frameworks, serializers, dependency injection, or tools that intentionally need internal access.

## 9. Reading the Exact Exception to Identify Which Permission Layer Is Missing

| Message/Error | Common Meaning | What to Check |
| --- | --- | --- |
| **package ... is not visible** | Compile-time code cannot use the package | **requires**, **exports**, module path |
| **IllegalAccessError** | Bytecode compiled, but runtime access is invalid | Module descriptors, module/JAR versions, runtime exports |
| **IllegalAccessException** | Reflection is not allowed to operate on the member | Modifiers, package export/open, caller module |
| **InaccessibleObjectException** | Request to enable access suppression was rejected by the module system | **opens**, qualified opens, **--add-opens** |
| **ClassNotFoundException** | Class not found by name in loader configuration | Classpath, module path, class loader |
| **NoSuchFieldException / NoSuchMethodException** | Member with requested name/signature not found | Name, parameter types, declaring class, library version |
| **InvocationTargetException** | Method invoked via reflection threw an exception internally | Inspect **getCause()** to find the method's actual error |

Do not confuse **InvocationTargetException** with an access permission error. It is a wrapper for an exception thrown by the target method itself after invocation occurred.

Similarly, **NoSuchMethodException** does not mean a module failed to open a package. The program may have looked up the wrong overload, wrong parameter types, or looked on a class that does not declare that method.

## 10. Diagnostic Workflow When Compilation Succeeds but Reflection Fails

Follow these steps in order to narrow down the issue quickly:

1. **Confirm the failing reflection operation.** Did the error occur at **getDeclaredField**, **trySetAccessible**, **Field.get**, **Method.invoke**, or **Constructor.newInstance**? Record the exact line throwing the error.
2. **Identify the member and package.** Note the module containing the class, the package, class, member, and access modifier.
3. **Identify the caller module.** Is the reflection code in a named module or the unnamed module on the classpath?
4. **Check exports.** If only public API access is needed, is the package exported to the caller?
5. **Check opens.** If private/package-private/protected deep reflection is needed, is the package opened to the caller?
6. **Check how the program is launched.** Do the IDE, test runner, container, or production command pass the right **--add-opens** flags?
7. **Check environment differences.** Compare JDK, module path, classpath, and dependency versions across local machine, CI, and production.
8. **Choose the narrowest fix.** Prefer opening the exact package to the exact module; avoid opening an entire module if only one package needs it.

You can use these commands to inspect configuration:

~~~bash
java -version
javac -version

# Inspect module descriptor and exported/opened packages
jar --describe-module --file libs/domain.jar

# Inspect module resolution at startup
java --show-module-resolution --module-path mods \
  -m com.example.framework/com.example.framework.Inspector

# Inspect where classes are loaded from (Java 9+)
java -Xlog:class+load=info --module-path mods \
  -m com.example.framework/com.example.framework.Inspector
~~~

When running on Windows PowerShell or CMD, you can write each command on a single line or use the line-continuation syntax appropriate for your shell.

## 11. Fixes That Easily Cause Problems

**Opening the entire module to fix one private field.** Using **open module** or **--add-opens ...=ALL-UNNAMED** grants broader access than needed. Prefer qualified **opens package to module** if you know which exact framework needs access.

**Exporting a package and expecting to read private fields.** **exports** grants public API access. Private fields require deep reflection and the package must be opened.

**Adding --add-opens to fix an import error.** Source code cannot import a package just because the package is opened. Use **exports** when public API access at compile time is needed.

**Calling setAccessible(true) on every field.** This easily couples your application to internal implementation details of libraries or the JDK. Prefer getters, constructors, public APIs, annotations, or extension points provided by the library.

**Opening JDK packages without reason.** Internal JDK packages are strongly encapsulated. If an old framework requires reflection into JDK internals, prefer upgrading the framework or moving to a supported API. Package-opening flags should only be compatibility measures with clear scope.

**Testing only with unit tests on one JDK.** Module configuration can differ between a test runner and the real application. Verify the actual launch command and JDK version in the target environment.

## 12. Choosing the Right Mechanism for Each Need

| Need | Mechanism to Use |
| --- | --- |
| Source code imports and calls another module's public API | **requires** and **exports** |
| Allow only one module to use a public API | Qualified **exports ... to ...** |
| Framework needs to read private fields or call private methods | Qualified **opens ... to ...** |
| Legacy application on classpath needs deep reflection | **--add-opens package=ALL-UNNAMED** at runtime, if truly needed |
| Library wants to support frameworks via reflection | Expose intentionally opened packages or provide clear APIs/extension points |
| Need dynamic access without private access | Reflection on exported public APIs or Method Handles with appropriate permissions |
| Need private access via Method Handles | **privateLookupIn** with module readability and open conditions satisfied |

A useful design principle: **Public APIs should be exposed with exports; internal details should be opened only to frameworks that truly need them with opens**. This helps modules preserve encapsulation boundaries and reduces coupling to internal structure.

## 13. Self-Check Questions

1. Does **getDeclaredField()** guarantee that **Field.get()** will succeed? Why or why not?
2. How do **exports** and **opens** differ in purpose and checking time?
3. Can a package that is **opens** but not **exports** be directly imported from another module?
4. When the caller runs on the classpath, what value can the target module in **--add-opens** be?
5. Why can **setAccessible(true)** throw **InaccessibleObjectException** even though the field exists?
6. If you only need to call a public method that is already exported, do you need to open the entire package?
7. What stage of execution does **InvocationTargetException** indicate the error occurred in?
8. If **trySetAccessible()** returns **false**, which descriptors or runtime options should you inspect?

If you can answer these questions, you can clearly distinguish errors caused by Java access modifiers, module readability/exports, or deep reflection. When investigating a real error, start from the failing reflection operation, identify the caller and target package, and then choose **exports** or **opens** to match the actual need.