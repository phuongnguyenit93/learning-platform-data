# Readability, exports, and opens in the Java Platform Module System (JPMS)

Readability, `exports`, and `opens` answer three different questions about module boundaries: **which module can be read**, **which public API can be used from outside**, and **which package allows deep reflection**. This lesson goes deeper into how these permissions work together, including `requires transitive`, `requires static`, qualified exports/opens, and runtime permissions that differ from declared ones.

Real-world symptom: the application calls public APIs normally, yet a framework fails at `Field.setAccessible(true)`. Readability and `exports` may already be complete; it is the package containing the field that has not been `opens`-ed to the module **actually performing Reflection**.

## 1. Modules, Packages, and Module Descriptors

A named module typically has a module-info.java file at the root of the module source. For example:

~~~java
module com.example.billing {
    requires java.sql;
    exports com.example.billing.api;
    opens com.example.billing.entity to com.example.framework;
}
~~~

Meaning:

- **requires java.sql**: the billing module reads module java.sql and can reference public types in packages that java.sql exports.
- **exports com.example.billing.api**: public types and public members have normal accessibility from modules that read billing, according to Java visibility rules.
- **opens com.example.billing.entity to com.example.framework**: module com.example.framework is allowed to perform *deep reflection* on package entity, including private fields/constructors, when APIs support suppressing access checks.
- Packages that are neither exported nor opened are **strongly encapsulated** against other modules, aside from the internal privileges of code within the module itself.

JPMS does not replace public/private/protected. A package-private class does not become public just because its package is exported; a private field does not become a public member just because its package is opened. JPMS adds **inter-module access boundaries** on top of existing Java visibility rules.

## 2. Readability: The requires Relationship Between Modules

**Readability** answers the question: "Can module A read module B?" In most named-module applications, A declares requires B so the compiler allows direct references to B's types.

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

- If app requires library, app reads library; however, **readability alone is not enough** to import a class in a non-exported package.
- Every named module reads **java.base** implicitly; there is no need to declare requires java.base.
- A module reads itself.
- Module.canRead(...) and module graph relationships can also be augmented when using module layers or JVM options; do not infer every permission solely from module-info.java while ignoring actual runtime configuration.

### requires transitive and requires static

Suppose app uses facade and facade uses api:

~~~text
com.example.app -> com.example.facade -> com.example.api
~~~

If facade only declares:

~~~java
module com.example.facade {
    requires com.example.api;
    exports com.example.facade;
}
~~~

then app requires facade but **does not automatically read api** just because facade reads api. When facade's public API exposes types belonging to api and you want consumers to read api through facade, you can use:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

Then a module reading facade also reads api via the transitive relationship. This **does not automatically export** api's packages: api must still export the needed packages.

**requires static** expresses a mandatory dependency at compile time, without requiring that dependency to be present and resolved at runtime. If the program actually uses a type from the optional module on a given execution path, missing that module can still cause an error. This is not a way to open Reflection.

You can check readability at runtime with **moduleA.canRead(moduleB)**; it returns a boolean, and checks only the module read edge, not per-package exports/opens.

## 3. Exports: Normally Accessible Public API

Declaration pattern:

~~~java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.spi to com.example.plugin;
}
~~~

- **exports p;** lets modules that have permission to read this module access public types/public members in package p using regular Java code.
- **exports p to m;** is a *qualified export*: it grants export permission only to target module m (or a specified list of modules); other modules cannot import API p by default.
- exports **does not permit arbitrary access to private fields/private methods** of classes in the package.
- exports affects only the declared package; it does not automatically export subpackages. For example, exports com.example.api **does not mean** exports com.example.api.internal.

For a given public class, the conditions for direct access from another named module include: the source module is readable, the package containing the class is appropriately exported, the class itself is public, and the member being used satisfies Java visibility rules.

If a package is not exported, a direct import statement from another module usually causes javac to report an error like "package ... is not visible". Adding requires in the caller module **does not solve** a missing exports error; you must revisit the API boundary or declare the appropriate exports.

## 4. Opens: Deep Reflection Permission

A framework such as a serializer, dependency injection container, or ORM often needs to read/assign private fields or invoke non-public constructors. Across two different modules, exports only grants access to public APIs, whereas **opens** allows Reflection to suppress access checks for all types/members in the opened package for the module performing Reflection.

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.model to com.example.serializer;
}
~~~

Key distinctions:

- **opens p;** opens package p to all modules for deep reflection.
- **opens p to m;** opens only to module m; this is the narrower choice when the framework is known.
- **open module name { ... }** opens all packages in the module for deep reflection at runtime. Inside an open module, you do not add per-package opens directives. An open module **does not automatically turn packages into exports for compile-time imports**.
- A package that is only opened is still not an API for another module's source code to import directly. The compiler enforces this based on declared exports.
- opens does not mean every Reflection call will succeed: you still need the right target object, parameter types, and error handling when invoking; meanwhile unopened packages may return false from trySetAccessible() or throw InaccessibleObjectException on setAccessible(true).

Related APIs:

| API | Purpose | Notes |
| --- | --- | --- |
| Class.getDeclaredField/getDeclaredMethod/getDeclaredConstructor | Look up non-public members as well | Getting metadata does not mean permission to use the member |
| AccessibleObject.setAccessible(true) | Request suppressing access checks for Reflection operations | May throw InaccessibleObjectException if JPMS does not permit it |
| AccessibleObject.trySetAccessible() | Attempt to enable access and receive a boolean | false when permission cannot be enabled under normal policy |
| Module.isOpen(package, targetModule) | Is the package open to targetModule? | True when qualified/unqualified opens applies |
| Module.isExported(package, targetModule) | Is the package considered exported **at runtime** to target? | A package opened to target is also treated as exported at runtime |
| Module.canRead(otherModule) | Does the current module read otherModule? | Does not replace checking exports/opens |

**Easy-to-misunderstand API detail:** As of JDK 17, if a package is **opens**-ed to module m, Module.isExported(package, m) can return **true** because the JVM treats an opened package as exported to that module **at runtime**. This **does not mean** module-info.java has exports or that javac allows importing classes from a package that is only opened. To inspect **declared** exports, read **Module.getDescriptor().exports()**.

## 5. Runnable Example: requires + exports + opens in Java 17+

We create two named modules:

- **com.acme.library** exports a public API package, and also opens an internal package specifically to client.
- **com.acme.client** requires library; calls the public API using normal Java syntax and uses Reflection to read a private field in the internal package.

### 5.1. Directory Structure

In the project directory, create the exact following files:

~~~text
src/
├── com.acme.library/
│   ├── module-info.java
│   └── com/acme/library/
│       ├── api/Service.java
│       └── internal/Secret.java
└── com.acme.client/
    ├── module-info.java
    └── com/acme/client/Main.java
~~~

**File src/com.acme.library/module-info.java:**

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.internal to com.acme.client;
}
~~~

**File src/com.acme.library/com/acme/library/api/Service.java:**

~~~java
package com.acme.library.api;

public final class Service {
    private Service() {}

    public static String greet() {
        return "hello";
    }
}
~~~

**File src/com.acme.library/com/acme/library/internal/Secret.java:**

~~~java
package com.acme.library.internal;

public final class Secret {
    private final String token = "hidden";
}
~~~

Class Secret is public to make it clear that **a public class in a non-exported package still cannot be imported directly from client**. Secret's constructor is not explicitly declared, so does Java generate a default constructor matching the class's public visibility? **No**: the default constructor has the same access as a public class, so in this case it is public. Even so, because package internal is only opened to client, Reflection still needs to enable access when calling the constructor from another module.

**File src/com.acme.client/module-info.java:**

~~~java
module com.acme.client {
    requires com.acme.library;
}
~~~

**File src/com.acme.client/com/acme/client/Main.java:**

~~~java
package com.acme.client;

import com.acme.library.api.Service;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module client = Main.class.getModule();
        Module library = Service.class.getModule();

        System.out.println("reads=" + client.canRead(library));
        System.out.println("api exported="
                + library.isExported("com.acme.library.api", client));

        boolean declaredInternalExport = library.getDescriptor().exports().stream()
                .anyMatch(e -> e.source().equals("com.acme.library.internal"));
        System.out.println("internal declared export=" + declaredInternalExport);
        System.out.println("internal runtime exported="
                + library.isExported("com.acme.library.internal", client));
        System.out.println("internal open="
                + library.isOpen("com.acme.library.internal", client));

        System.out.println("greet=" + Service.greet());

        Class<?> secretType = Class.forName("com.acme.library.internal.Secret");
        Constructor<?> ctor = secretType.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object secret = ctor.newInstance();

        Field field = secretType.getDeclaredField("token");
        field.setAccessible(true);
        System.out.println("token=" + field.get(secret));
    }
}
~~~

### 5.2. Compiling and Running

In the directory containing src, run using JDK 17 or later:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.library,com.acme.client
java --module-path mods --module com.acme.client/com.acme.client.Main
~~~

The syntax above does not rely on shell glob expansion; it can be run similarly in Windows PowerShell and other common shells. **--module-source-path src** tells javac the multi-module layout, **-d mods** places output in the mods directory, **-m** selects modules to compile, and **--module-path mods** and **--module name/package.Main** specify the module/class to run.

Stdout, actually verified when compiling source with **--release 17** and running on JDK 21:

~~~text
reads=true
api exported=true
internal declared export=false
internal runtime exported=true
internal open=true
greet=hello
token=hidden
~~~

### 5.3. Why Can the Private Field Be Read?

- **reads=true**: client declares requires library.
- **api exported=true**: library exports com.acme.library.api, so importing and calling Service.greet() succeeds.
- **internal declared export=false**: module-info.java does not declare exports for package internal.
- **internal runtime exported=true**: the Java Module API treats a package that is **opens to client** as exported **at runtime** for client. This value does not mean the compiler allows importing Secret.
- **internal open=true**: client is granted deep Reflection access to package internal. Both the constructor and private field require setAccessible(true) to bypass Java/JPMS access checks.
- **token=hidden**: once permitted, Field.get() reads the private instance field on the Secret object.

If you add import com.acme.library.internal.Secret; to Main.java, javac rejects it because the package is only opened, **not exported**. The running code does not use that import; it loads the class by name and performs Reflection within the granted opens scope.

## 6. Try Changing Permissions and Predict Errors

### Case A: requires present, but API exports missing

Change library's module-info.java to:

~~~java
module com.acme.library {
    opens com.acme.library.internal to com.acme.client;
}
~~~

When recompiling the same Main.java, import com.acme.library.api.Service is rejected because package api is not exported. Keeping requires in client **is not enough**. The proper fix is to restore exports com.acme.library.api or change the architecture so client does not directly reference that API.

### Case B: API exports present, but internal opens missing

Change library's module-info.java to:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Main's source still compiles (since it does not import internal.Secret). However, at runtime when reaching ctor.setAccessible(true), the JVM does not let client enable access to the constructor of a class in an internal package that is not opened to client, resulting in **java.lang.reflect.InaccessibleObjectException**. Restore opens ... to com.acme.client, or grant appropriately scoped open permission at launch.

### Case C: internal exported, but internal not opened

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.internal;
}
~~~

Client can use Secret's public API from regular Java code, yet **cannot arbitrarily read the private field token** with Field.setAccessible(true). Reflection into private members from another module requires opens (or another valid permission mechanism). This is the fundamental difference between exports and opens.

### Case D: opens without to

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.internal;
}
~~~

Any module eligible to perform Reflection at runtime can request deep reflection on package internal. Broaden access like this only when needed; when the framework module name is known, **opens ... to framework.module** expresses the permission boundary more clearly.

## 7. Modifying Runtime Permissions with --add-reads, --add-exports, --add-opens

While migrating legacy applications to JPMS, launcher/compiler options are sometimes needed to adjust the module graph and accessibility:

| Option | Primary Meaning | What It Does Not Solve |
| --- | --- | --- |
| --add-reads A=B | Allows module A to read module B | Does not automatically export or open B's packages |
| --add-exports A/p=B | Grants B access to public APIs in package p of A | Does not allow Reflection into private members |
| --add-opens A/p=B | Opens package p of A for deep reflection from B | Does not turn the package into a directly importable API when compiling source code |

For example, if a compiled library lacks the needed opens, you can test once with a **runtime** option:

~~~bash
java --module-path mods --add-opens com.acme.library/com.acme.library.internal=com.acme.client --module com.acme.client/com.acme.client.Main
~~~

This command lets module com.acme.client deep-reflect package internal without editing compiled classes or module-info. In the original example, opens is already declared so this option is **unnecessary**. If you test Case B (removing opens from module-info), the option above restores Reflection permission.

For applications on the classpath, that code belongs to the *unnamed module*; the special target name **ALL-UNNAMED** is used to open to unnamed modules, such as --add-opens java.base/java.lang=ALL-UNNAMED. However, do not blindly open JDK packages or the whole application: identify the exact caller module, exact package, and reason deep reflection is needed. Since Java 17, access to JDK internals is more strongly encapsulated; an InaccessibleObjectException is a signal to prefer public APIs or intentional opens configuration.

For **--add-exports** supporting direct imports, appropriate configuration is sometimes needed **both at compile time and at runtime**; a runtime change alone does not fix javac errors at compile time. The **--add-opens** option targets runtime Reflection checks and does not replace exports for compiling imports.

## 8. How Does Readability Relate to Reflection?

Normally, Java source requires both module readability and exports to reference an external public class. Reflection has a specific trait: when checking access on reflective objects, the API **assumes readability**; that is why you can look up a class by name and use Reflection in some cases where source code could not import it. However, Reflection **does not bypass module encapsulation**: the package must be appropriately exported for public access or appropriately opened when deep reflection is desired.

This example intentionally declares requires in client so the dependency path is explicit; Class.forName is not a substitute for module configuration in source code that depends on a library.

Opening a package with opens is typically required for techniques such as Field.setAccessible(true), Constructor.setAccessible(true), Method.setAccessible(true), and MethodHandles.privateLookupIn when the caller module differs from the module containing the type. The Module.isOpen(package, callerModule) API is a useful check for diagnostics.

Do not confuse **finding** a Field/Method via getDeclared... with **being permitted to invoke** it. getDeclaredMethods() can list private members, yet invoke/get/set or setAccessible must still obey access rules.

## 9. Workflow for Diagnosing Module Errors When Using Reflection

1. **Identify the actual caller module:** where setAccessible/MethodHandles lookup is executed, which may be a framework module rather than the application module. Use SomeClass.class.getModule() or stack trace details.
2. **Identify the module containing the class and package:** targetClass.getModule(), targetClass.getPackageName(). Do not confuse a class's package with the module name.
3. **Check readability and exports:** moduleCaller.canRead(moduleTarget) helps analyze dependencies; the package must be appropriately exported if public APIs are used from source code.
4. **Check opens for the right caller:** moduleTarget.isOpen(packageName, moduleCaller) must match when private reflective access is needed.
5. **Compare module-info.java with runtime reality:** use Module.getDescriptor().exports()/opens() to inspect declarations and remember that Module.isExported can be true when opened at runtime.
6. **Fix with the right scope:** prefer declaring exports for truly public APIs, opens ... to framework for data binding/serialization, or an alternative public API. Use targeted launcher flags only when needed for compatibility or verifying root cause.

**Quick example:** the error "module A does not 'opens p' to module B" indicates that B is the module performing Reflection; adding requires A in B **does not** grant permission to open private fields in p. Look into opens p to B in A or the corresponding runtime configuration.

## 10. Common Mistakes and Self-Check Exercises

- **"`requires` lets you use every package":** false; you must consider exports and visibility, and private Reflection also requires opens.
- **"`exports` also allows `setAccessible` into private members":** false. exports serves public member access under Java rules; opens is for deep reflection.
- **"`opens` allows importing at compile time":** false. Opens is a Reflection/runtime permission; exports exposes APIs to javac.
- **"`Module.isExported` true guarantees `exports` is in `module-info.java`":** false when the package is opened to the caller. Check ModuleDescriptor.exports() if you want to confirm declared exports.
- **"Opening `com.example.model` also opens `com.example.model.internal`":** false; each package has its own boundary.
- **"You can always call `setAccessible(true)` since the member was found":** false, especially with named modules.
- **"Using `--add-opens` everywhere solves modularity":** overly broad configuration hides API design flaws, hurts maintainability, and widens internal access exposure.

Check yourself on three scenarios:

1. Module A requires B, yet B's package b.internal is not exported. Can A import b.internal.Secret? **No**; A reads B, but B has not exported that package.
2. B exports b.api and does not open b.api. Can A call a public method on a public class in b.api if it requires B? **Yes**. Can A use setAccessible(true) to access a private field of that class? **No**, unless another valid access permission exists.
3. B opens b.entity to framework.orm and does not export b.entity. Can module framework.orm use private reflection on b.entity with the proper API and open permission? **Yes**. Can another app module import b.entity.Entity in its source code based solely on that opens? **No**.

**Takeaway:** **requires** establishes module readability, **exports** provides public APIs across modules, and **opens** grants deep Reflection permission for a package. All three must be checked **separately**, especially when invoking Reflection from a framework in another module.

### References

- JLS 17 — §7.7 Module Declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7
- Java SE 17 — Class Module API (canRead/isExported/isOpen): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 — AccessibleObject API and setAccessible: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- JEP 261 — Module System: https://openjdk.org/jeps/261
- JEP 403 — Strongly Encapsulate JDK Internals: https://openjdk.org/jeps/403
