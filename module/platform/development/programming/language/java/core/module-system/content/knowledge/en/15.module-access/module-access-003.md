# Package-Private and Private Remain Restricted in the Java Module System

## 1. Lesson Objectives

When learning the Java Platform Module System (JPMS), we often encounter declarations such as **requires**, **exports**, and **opens** in **module-info.java**. They control relationships between modules, but **they do not change the member access rules of the Java language**.

After this lesson, you will be able to:

- Distinguish **public**, **protected**, **package-private**, and **private** access levels from module-level access control.
- Explain why an **exported** package still does not make package-private or private members directly callable from another module.
- Understand the difference between normal access and access through **reflection** when a package has **opens**.
- Write and run a two-named-module example to observe valid cases, compile errors, and runtime access errors.
- Know when to design a public API, when to use scoped **opens**, and why you should not open an entire module's internals just to bypass access errors.

## 2. Two Separate Layers of Access Control

Java asks at least two independent questions when a piece of code wants to use a class or member:

1. **At the module level:** Does the calling code's module **read** the module containing that class? Is the package containing the class **exported** to the calling module?
2. **At the Java language level:** Do the class itself and the member have modifiers appropriate for the call site, such as **public**, **protected**, **package-private**, or **private**?

For normal Java access from another module, **both layers of conditions must be satisfied**.

~~~text
Module com.example.app
        |
        | requires com.example.library
        v
Module com.example.library
        |
        | exports com.example.library.api
        v
public class User
        |
        +-- public String getName()       --> callable via public API
        +-- String internalNote()         --> package-private: not callable
        +-- private String secret()        --> private: not callable
~~~

Therefore, **exporting a package is not equivalent to turning every class and member in the package into public**. JPMS controls which packages are exposed to other modules; Java modifiers still decide who can access a class or member.

## 3. Review of Java's Four Access Levels

| Member modifier | Inside declaring class | Code in same package | Code in another package |
| --- | --- | --- | --- |
| **public** | Yes | Yes | Yes, if the class/package is also accessible |
| **protected** | Yes | Yes | Primarily via inheritance, following protected rules |
| **package-private** (no modifier written) | Yes | Yes | No |
| **private** | Yes | No, except for cases such as nestmates | No |

Important notes:

- **Package-private** is not a Java keyword; it is the default access level when **public/protected/private** is omitted.
- **Private** restricts access to the class or its corresponding **nest**; since Java 11, classes that are **nestmates** can access each other's private members under Java rules. This is not a permission granted by JPMS.
- A top-level class can only be **public** or **package-private**; protected and private do not apply directly to top-level classes.
- For **protected** in another package, a subclass must also follow the type rules on the access expression; inheriting alone does not allow calling it on arbitrary instances of the superclass.
- Having permission to see a **public class** does not mean having permission to read its private fields or call its package-private methods.

If two modules have the same package name, you must not assume that creates package-private access between them. In a modular environment, module relationships and runtime packages/class loaders have their own constraints; treat the **module API** as the exchange boundary and avoid designs relying on sharing package names across modules.

## 4. exports: Exposing a Package Containing a Public API

Example library module:

~~~java
// src/com.example.library/module-info.java
module com.example.library {
    exports com.example.library.api;
}
~~~

Class in the exported package:

~~~java
// src/com.example.library/com/example/library/api/User.java
package com.example.library.api;

public class User {
    private final String token = "demo-token";

    public String getName() {
        return "An";
    }

    String internalNote() { // package-private
        return "Used only within the package";
    }

    private String secretNote() {
        return "Internal to User class";
    }
}
~~~

Consumer module:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.library;
}
~~~

Inside module **com.example.app**, the following is valid:

~~~java
import com.example.library.api.User;

User user = new User();
System.out.println(user.getName()); // Valid: public API
~~~

However, the following statements **do not compile**:

~~~java
user.internalNote(); // Invalid: package-private
user.secretNote();   // Invalid: private
System.out.println(user.token); // Invalid: private
~~~

Reasons:

- **requires com.example.library** lets the app module **read** the library module.
- **exports com.example.library.api** lets the app module access **public types** in that package.
- **User** is public; **getName()** is also public, so it can be called.
- **internalNote()** is package-private; code in package **com.example.app** does not belong to the package declaring the method.
- **secretNote()** and **token** are private; **exports** does not alter modifiers.

This is the core distinction of the lesson: **JPMS adds access conditions; it does not remove existing Java access conditions**.

### 4.1. When the Package Is Not Exported

If the library module is changed to:

~~~java
module com.example.library {
    // Does not export com.example.library.api
}
~~~

then even importing **User** from the app module is rejected at compile time because the package is not exported to the app module. Simply having class **User** be public is not enough.

### 4.2. Qualified Exports Do Not Allow Calling Private Members

A module can export a package only to selected modules:

~~~java
module com.example.library {
    exports com.example.library.api to com.example.app;
}
~~~

Module **com.example.app** still can only use the public API allowed by the Java language. This selective export **does not grant extra** access to package-private or private members.

## 5. Package-Private Remains Usable Within the Package

Suppose in the same package **com.example.library.api**, we add:

~~~java
// src/com.example.library/com/example/library/api/SamePackageDemo.java
package com.example.library.api;

public final class SamePackageDemo {
    private SamePackageDemo() {}

    public static String readInternalNote(User user) {
        // Valid: SamePackageDemo and User are in the same package.
        return user.internalNote();
    }

    // Invalid:
    // return user.secretNote();
    // return user.token;
}
~~~

**SamePackageDemo** can call **internalNote()** because it is in the same package as **User**. If the library wants the app module to receive the result, it can intentionally expose a public API such as **SamePackageDemo.readInternalNote(User)**.

This **does not make internalNote public**; the library is deliberately exposing a safe operation through its public API surface.

This example also shows the difference between:

- **Permissions of intra-package code**: can access package-private members.
- **Permissions of another module via exports**: can only access APIs permitted by Java and located in an exported package.

Package-private is a useful tool for sharing helpers, factories, or implementation logic within a package without expanding the public API.

## 6. opens for Reflection: Not Normal Java Access

**opens** serves **deep reflection**, such as an ORM, serialization, or dependency injection framework needing to access a non-public field/constructor/method through reflection APIs.

Example:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.app;
}
~~~

The two lines handle two different responsibilities:

- **exports** allows code in app to reference **User** directly and call public methods.
- **opens ... to com.example.app** allows code in app to perform deep reflection on that package, such as calling **Field.setAccessible(true)** and reading a private field.

**opens does not make user.internalNote() or user.secretNote() compile.** The Java compiler still enforces modifiers as usual.

### 6.1. Reflection Takes Two Steps

Observe reflection:

~~~java
import com.example.library.api.User;
import java.lang.reflect.Field;

User user = new User();
Field field = User.class.getDeclaredField("token");
field.setAccessible(true);       // Attempts to enable deep reflective access
Object value = field.get(user);  // Reads the permitted field
System.out.println(value);
~~~

With **opens com.example.library.api to com.example.app**, the snippet above can succeed from the app module.

If **opens** is removed, calling **setAccessible(true)** can throw **java.lang.reflect.InaccessibleObjectException** because the package containing the field is not open to the caller's module. **getDeclaredField** can find metadata about the member, but finding metadata does not automatically grant permission to use the member.

Where the API allows, **trySetAccessible()** can be used to check and receive **false** instead of expecting every **setAccessible(true)** call to always succeed:

~~~java
Field field = User.class.getDeclaredField("token");
if (field.trySetAccessible()) {
    System.out.println(field.get(user));
} else {
    System.out.println("Deep reflection is not permitted");
}
~~~

Reflective access should not be treated as the default way to use private APIs. It couples code to implementation details and easily breaks when fields are renamed or libraries are upgraded.

### 6.2. exports Does Not Replace opens and Vice Versa

| Declaration in library module | App imports User and calls getName() | App directly calls internalNote()/secretNote() | Deep reflection on private field |
| --- | --- | --- | --- |
| **exports api;** | Yes | No | Usually blocked when caller is in another module |
| **opens api to app;** | No, without an appropriate exports | No | Possible, when caller is the opened app module |
| **exports api; opens api to app;** | Yes | No | Possible, when caller is the opened app module |
| Neither exports nor opens | No | No | Usually blocked |

In the table, **api** is shorthand for package **com.example.library.api**, and **app** is module **com.example.app**.

For reflection on public members of a public class in an exported package, the rules can allow access without **opens**. **opens** becomes essential when code needs to bypass normal Java access checks for non-public members or classes.

## 7. Complete Practice with Two Named Modules

The example below combines **exports**, **opens**, package-private, and private in a runnable program.

### 7.1. Directory Structure

~~~text
src/
  com.example.library/
    module-info.java
    com/example/library/api/
      User.java
      SamePackageDemo.java
  com.example.app/
    module-info.java
    com/example/app/
      Main.java
~~~

**src/com.example.library/module-info.java**:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.app;
}
~~~

**src/com.example.library/com/example/library/api/User.java**:

~~~java
package com.example.library.api;

public final class User {
    private final String token = "demo-token";

    public String getName() {
        return "An";
    }

    String internalNote() {
        return "package-private OK within package";
    }

    private String secretNote() {
        return "private belongs only to User logic";
    }
}
~~~

**src/com.example.library/com/example/library/api/SamePackageDemo.java**:

~~~java
package com.example.library.api;

public final class SamePackageDemo {
    private SamePackageDemo() {}

    public static String readInternalNote(User user) {
        return user.internalNote();
    }
}
~~~

**src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.library.api.SamePackageDemo;
import com.example.library.api.User;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Exception {
        User user = new User();

        // (1) Access via public API in exported package.
        System.out.println("Public: " + user.getName());

        // (2) Code in the same library package accesses package-private.
        System.out.println("Package: "
                + SamePackageDemo.readInternalNote(user));

        // The following two statements do not compile due to Java access modifiers:
        // user.internalNote();
        // user.secretNote();

        // (3) App is granted opens on the package, so deep reflection is permitted.
        Field tokenField = User.class.getDeclaredField("token");
        tokenField.setAccessible(true);
        System.out.println("Private field via reflection: "
                + tokenField.get(user));

        Method privateMethod =
                User.class.getDeclaredMethod("secretNote");
        privateMethod.setAccessible(true);
        System.out.println("Private method via reflection: "
                + privateMethod.invoke(user));
    }
}
~~~

### 7.2. Compiling and Running

In the parent directory containing **src/**, using JDK 17 or later:

~~~bash
javac --module-source-path src -d mods -m com.example.library,com.example.app
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Expected output:

~~~text
Public: An
Package: package-private OK within package
Private field via reflection: demo-token
Private method via reflection: private belongs only to User logic
~~~

This example **demonstrates the mechanism**: a real-world application should not extract tokens/secrets via reflection simply because it is possible to do so.

### 7.3. Three Useful Experiments

**Experiment A — remove opens:** Delete the line **opens com.example.library.api to com.example.app;**, then recompile and rerun. Calling **getName()** and **SamePackageDemo.readInternalNote()** still works, but calling **setAccessible(true)** on the private field is no longer allowed from the app module.

**Experiment B — remove exports:** Keep **opens** but remove **exports**. App code that still directly imports **User** and **SamePackageDemo** will fail to compile. To perform pure reflection in an opens-only configuration, you must write the app without static references to those classes, loading the classes and performing reflection according to module rules.

**Experiment C — add direct calls:** Uncomment **user.internalNote()** or **user.secretNote()**. The Java compiler rejects them even though the library module has both **exports** and **opens**. This is the key takeaway to remember.

## 8. Why --add-exports and --add-opens Still Do Not Turn Private into Public

Some JPMS errors suggest using launcher options:

~~~bash
java --add-exports com.example.library/com.example.library.api=com.example.app ...
java --add-opens com.example.library/com.example.library.api=com.example.app ...
~~~

Meaning:

- **--add-exports** grants additional package export permission to the target module in that environment; it allows using **public types/members** that Java permits access to.
- **--add-opens** opens the package for **deep reflection** to the target module at runtime.
- Neither option **rewrites Java member modifiers**. Directly calling package-private/private members from another package still violates language rules.

For precompiled code, distinguish **javac** options from **java** options: extra permissions at runtime cannot fix an access error that already occurred at compile time. Do not rely on flags as a substitute for a stable public API contract.

## 9. Common Misconceptions

### "Once a module requires a dependency, it can call all classes in that dependency"

False. **requires** establishes module-level readability; code still needs an exported package and valid class/member access permissions. A module can be readable while keeping most of its implementation packages hidden.

### "Once a package is exported, package-private becomes public"

False. **exports** applies to public APIs accessible under Java rules. Package-private methods remain limited to code in the same package.

### "opens allows calling private methods normally"

False. **opens** only opens the path for supported reflection mechanisms after code invokes the corresponding reflection APIs. Calling **user.secretNote()** directly is still rejected by the compiler.

### "setAccessible(true) always succeeds"

False. JPMS enforces strong encapsulation and can block deep reflection when a package is not open to the calling module. Calling **setAccessible** can throw **InaccessibleObjectException**. Success also depends on the specific access case.

### "Putting a class in a package with the same name in another module grants package-private access"

Do not assume this. In JPMS, identical package names do not mean they share a runtime package scope with identical access permissions. Named modules also have constraints involving split packages, class loaders, and module resolution. Keep internal classes in their proper module/package, or design a clear public API.

### "Private can always only be accessed by the declaring class"

In modern Java, there is the **nestmates** exception for classes in the same nest, such as outer/nested classes. However, this is a Java access rule, not a feature of **requires**, **exports**, or **opens**.

## 10. Designing a Module API Properly

When building a library or multi-module system:

1. Place **supported APIs** in clearly named packages, with public classes and necessary public members, and declare **exports** for those packages.
2. Keep helpers and package-private implementations inside the owning package/module. Use private for state and details meant only for the class/nest.
3. Leave implementation packages unexported if external code should not use them directly.
4. If a framework needs deep reflection, **opens only the relevant package to the specific framework module** when feasible, for example **opens com.example.library.model to org.hibernate.orm.core;** using the actual module name of the library version in use.
5. Prefer constructors, interfaces, factories, DTOs, and intentional public APIs. Reflection should be a choice with a clear reason and well-defined contract.
6. Do not let "making it run with --add-opens" mask a poorly designed dependency boundary.

A common design pattern:

~~~java
module com.example.order {
    exports com.example.order.api;

    // Only frameworks that need reflection on the model should open this package:
    // opens com.example.order.model to actual.framework.module.name;
}
~~~

In the example above, the **opens** line is commented out to emphasize that you must substitute the actual framework module name before applying it. Public APIs and implementation packages are managed according to specific needs; there is no need to expose everything.

## 11. Review Questions

1. Module A declares **requires B**, and B declares **exports b.api**. Why can A still not call a package-private method on a public class in **b.api**?
2. How do **exports b.api** and **opens b.api to a** differ for the compiler and for reflective access?
3. If **opens** is removed in the hands-on example, which line is likely to throw **InaccessibleObjectException**?
4. Can a public method in a public class inside an unexported package be directly imported from another named module? Why or why not?
5. When can code in the same package access a package-private member? Why does that not permit arbitrary classes from another module with the same package name to do so?
6. Why does a good plugin/framework design typically rely on stable public service interfaces instead of reflecting into a plugin's private members?
7. Does using **--add-exports** allow calling **user.secretNote()** directly? Does using **--add-opens** make the compiler accept that call?

## 12. Key Takeaways

**JPMS enforces access at the module level, whereas Java modifiers enforce access at the class/member level.** For a normal call from another module to work, the calling module must read the provider module, the package must be appropriately exported, and the class/member must have an access level permitted by Java.

**Package-private remains package-private; private remains private**, even when the package is **exported**. **opens** permits certain deep reflection operations, but it does not change direct invocation under Java syntax.

References:

- [Java Language Specification, Chapter 6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html) (scope of names and accessibility).
- [Java Language Specification, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html) (package/module declarations, exports, and opens).
- [java.lang.reflect.AccessibleObject — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html) (rules governing reflective access).