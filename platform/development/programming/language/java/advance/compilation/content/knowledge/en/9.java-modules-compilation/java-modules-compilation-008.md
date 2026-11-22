# Distinguishing Compile-Time Access from Runtime Reflection Configuration in Java Modules

In the Java Platform Module System (**JPMS**, available since Java 9), a class declared **public** is not necessarily accessible from another module. When a program uses a library, two needs must be distinguished:

- **Static compile-time access:** source code wants to **import, call constructors or methods, or access fields** through normal Java access rules. JPMS uses module read relationships (**readability**) and **exports**-ed packages, together with access modifiers such as public/protected/private, to decide.
- **Runtime reflective access:** a framework wants to **locate classes, read annotations, instantiate objects, or read/write fields using java.lang.reflect**. If it only calls normally accessible public members, exports may be enough. If it needs **deep reflection** to suppress access checks on private/package-private members, the module owning the package usually must **opens** that package to the module performing reflection.

These two configurations govern different permissions. **requires + exports** does not automatically allow reading private fields; **opens** does not turn a package into an API that can be imported at compile time.

## 1. Context: Packages and Modules Have Two Boundary Layers

A package groups related types and is governed by language access rules (public, protected, package-private, private). A **named module** groups multiple packages and describes dependencies along with which packages external code is allowed to use.

Example:

~~~text
module demo.model
├── demo.model.api
│   └── Greeting.java       (published API)
└── demo.model.internal
    └── Secret.java         (internal code)

module demo.consumer
└── demo.consumer
    └── Main.java
~~~

Even when both Greeting and Secret are **public class**, module demo.model may expose only package demo.model.api. In that case, code in demo.consumer can use Greeting directly if it has an appropriate readability relationship, yet cannot import Secret from an unexported package. This is **strong encapsulation at the module level**.

**Why add a module level?** Before JPMS, a public class on the classpath could usually be imported from another package. Once a JAR becomes an explicit named module on the module path, the module descriptor can hide entire implementation packages even when they contain public classes. A true public API must be intentionally exposed.

## 2. Concepts That Must Not Be Confused

| Concept | Rule | Primary effect |
| --- | --- | --- |
| **public class / public method** | Java access modifier | Checks access at the type/member level; does not bypass module boundaries |
| **requires module.name** | Current module declares dependency on and reads target module | Prerequisite for code to use APIs from another named module |
| **exports some.pkg** | Exposes package to every module reading the owning module | Allows accessing public API at compile time and runtime |
| **exports some.pkg to friend.module** | Exposes only to the listed module(s) | Restricted-audience API |
| **opens some.pkg** | Opens package for runtime reflection | Allows deep reflection into non-public members from other modules |
| **opens some.pkg to framework.module** | Opens only to the specified module(s) | Limits the scope of deep reflection |
| **open module demo.model** | Opens all packages of the module for reflection | Relaxes reflection permissions across the whole module |
| **--add-exports** | Tool option adding an export in the relevant run/compile scope | Workaround for accessing an unexported API |
| **--add-opens** | Launcher option opening a package at runtime | Workaround for deep reflection |
| **setAccessible(true)** | Requests bypassing Java access checks in reflection | Succeeds only when JPMS permission conditions allow |

According to the Java Language Specification, **exports** enables other modules to access public/protected types and members when readability and ordinary Java permissions are satisfied. **opens** permits reflection at runtime, including non-public types/members; it **does not grant compile-time import permission** for an unexported package.

For part of a public API that has already been exported, normal reflection can invoke public methods/constructors without needing opens. Only when access checks need to be suppressed, such as touching a private field, does deep reflection become the issue.

## 3. Readability: requires Resolves Relationships Between Modules

Suppose the application module needs to use the library module:

~~~java
module demo.consumer {
    requires demo.model;
}
~~~

This declaration states that demo.consumer **reads** demo.model. It does not automatically export every package of demo.model. If the library module declares:

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

then demo.consumer can import public types from **demo.model.api**. However, **demo.model.internal** remains closed because it has no exports.

Two conditions must work together:

1. The consuming module must read the providing module (**requires**, or another valid readability relation).
2. The package containing the type must be exported to the consuming module; types and members must also satisfy Java access rules.

For example: if demo.consumer has requires yet demo.model does not export demo.model.api, importing public Greeting still fails. Conversely, if demo.model already exports yet demo.consumer lacks requires, the compiler does not infer readability from an import statement either.

**Do not equate requires with the classpath.** The two named modules in the example are typically compiled/run on the **module path**, whereas classpath programs belong to the **unnamed module** with different observability/readability rules. When analyzing JPMS errors, clearly determine whether code runs on the classpath, module path, or a mix of both.

## 4. exports: Permission to Use Public APIs at Compile Time

In the library's module-info.java:

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

Only package **demo.model.api** is exported. For a client module with proper requires, the following statement is valid if Greeting is public:

~~~java
import demo.model.api.Greeting;
~~~

However, a public **class** alone is not enough if a method is declared private. Example:

~~~java
package demo.model.api;

public class Greeting {
    public static String hello() {
        return "Xin chào";
    }

    private static String internalToken() {
        return "hidden";
    }
}
~~~

The client can call Greeting.hello(), yet cannot call Greeting.internalToken() as a normal Java method. **exports does not turn private into public.**

If a module only wants to expose an API to a friend module:

~~~java
module demo.model {
    exports demo.model.api to demo.consumer;
}
~~~

This is a **qualified export**. Other modules not listed do not have access to the API via standard module relationships. Even with a qualified export, access modifiers within the package remain in force.

### 4.1. exports and normal reflection

For example, a client has a public class in an exported package with a public method. Normal reflective access such as locating the public method via getMethod and calling invoke is generally permitted (with appropriate objects and access permissions); opens is not needed merely because the client's API uses reflection.

The difference arises only when the client wants to access restricted members and uses **setAccessible(true)** or **trySetAccessible()**. An exported package **does not automatically allow** another module to bypass private/protected/package-private access.

### 4.2. A qualified export is not opens

The declaration:

~~~java
exports demo.model.api to demo.consumer;
~~~

grants API access to demo.consumer, yet does not mean demo.consumer is granted deep reflection into private fields in that package. If genuinely needed, the descriptor can declare both:

~~~java
exports demo.model.api to demo.consumer;
opens demo.model.api to demo.consumer;
~~~

The two lines have different effects. Add opens only when there is a clear reflection use case; if the framework only needs public APIs, there is no need to open private members.

## 5. opens: Reflection Permission at Runtime

Certain frameworks (dependency injection, ORM, JSON/XML binding, serializers, test tools) may need to instantiate objects via non-public constructors, read annotations on private fields, or assign field values through reflection.

A descriptor can grant permission as follows:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

Meaning:

- **demo.model.api** remains the published API for Java code in other modules to use statically.
- **demo.model.internal** is not exported, so demo.consumer **cannot directly import classes there** solely because of opens.
- demo.consumer is permitted to request reflective access to types/members of demo.model.internal at runtime, including private ones if using appropriate reflection APIs.
- Modules not named in **to demo.consumer** do not receive deep reflection permission from this declaration.

If **to demo.consumer** is omitted:

~~~java
opens demo.model.internal;
~~~

the package is opened for reflection to all modules, a broader scope. When the framework module actually needing permission is known, **qualified opens** is usually clearer and narrower.

**Important point:** opens does not run reflection by itself. Java code must actually call APIs such as Class.forName, getDeclaredField, getDeclaredConstructor, setAccessible, or equivalent framework tooling. Opens merely removes the barrier at the module boundary for allowed operations.

### 5.1. How do setAccessible and trySetAccessible differ?

When calling:

~~~java
field.setAccessible(true);
~~~

Java checks whether the caller can disable access checks for that field. If the package is in another named module and has not been opened appropriately, the operation may throw **java.lang.reflect.InaccessibleObjectException**.

The form that does not throw an exception when only the corresponding permission is insufficient:

~~~java
boolean allowed = field.trySetAccessible();
~~~

If enabling access is not permitted, trySetAccessible typically returns **false**, helping code proactively handle situations where the framework lacks opens. This is still a permission-checked operation, not a way to bypass encapsulation. Other exceptions may still occur depending on the reflection object and security context.

For a **public member of a public class in an exported package**, normal reflective access can succeed without calling setAccessible. For a **cross-module private member**, opens and a valid suppress-access request are normally required.

### 5.2. Opening a package does not mean objects appear on their own

Class.forName can load a class by fully qualified name when the class loader/module resolution locates that class. However, **finding/loading the Class object** and **having permission to create an instance or read a field** are two separate questions. A class in an unexported package may be found by reflection, then fail when code attempts to access its constructor due to Java access/module checks.

The illustrative example in section 7 uses this property to make the error clear.

## 6. Permission Matrix: Static Access and Reflection

Assuming the client in another module has an appropriate readability relationship, the type is declared **public**, and the user adds no command-line overrides:

| Package descriptor | Import/call public type at compile time? | Call public member via normal reflection? | Deep reflection into private field? |
| --- | --- | --- | --- |
| No exports, no opens | No | Not permitted to access members normally | No |
| **exports pkg;** | Yes | Yes (if Java access conditions hold) | No |
| **opens pkg;** | No | Reflective access possible at runtime | Yes, if using proper reflection APIs |
| **exports pkg; opens pkg;** | Yes | Yes | Yes |
| **exports pkg to M;** | Yes for M | Yes for M | Not from exports alone |
| **opens pkg to M;** | Not from opens alone | Possible for M | Yes for M |
| **open module ...** (without exports pkg) | No | Reflection possible at runtime | Yes |

The table represents the common model when modules/packages resolve properly. Reflective access permission also depends on the module **performing** reflection, member kind, access modifier, class loader, and API used. It does not mean every reflection call succeeds regardless of constructor/method name or argument values.

**A public type can be closed at the package level.** And a private field can remain closed to reflection even though the package has been exported. Those are two separate access layers.

## 7. Java 17+ Example: Two Modules, Public API, and Private Field

This example has two real modules runnable with JDK 17+. Module **demo.model** exports a public API package and keeps an internal package to test reflection. Module **demo.consumer** uses the static API, then attempts to read a private field via reflection.

### 7.1. Project structure

Create the files:

~~~text
src/
├── demo.model/
│   ├── module-info.java
│   └── demo/
│       └── model/
│           ├── api/
│           │   └── Greeting.java
│           └── internal/
│               └── Secret.java
└── demo.consumer/
    ├── module-info.java
    └── demo/
        └── consumer/
            └── Main.java
~~~

**File src/demo.model/module-info.java:**

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

No opens yet. This is the initial state to observe reflection being blocked.

**File src/demo.model/demo/model/api/Greeting.java:**

~~~java
package demo.model.api;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Public API OK";
    }
}
~~~

**File src/demo.model/demo/model/internal/Secret.java:**

~~~java
package demo.model.internal;

public final class Secret {
    private final String code = "vault-42";

    public Secret() {}
}
~~~

Secret is declared public to clearly illustrate the difference between a **public type** and an **exported package**. Package demo.model.internal is still not exported, so the client cannot import Secret directly. Field code is private, so even exporting the package does not allow external code to read the field directly.

**File src/demo.consumer/module-info.java:**

~~~java
module demo.consumer {
    requires demo.model;
}
~~~

**File src/demo.consumer/demo/consumer/Main.java:**

~~~java
package demo.consumer;

import demo.model.api.Greeting;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(Greeting.message());

        Class<?> secretType =
                Class.forName("demo.model.internal.Secret");

        Constructor<?> constructor =
                secretType.getDeclaredConstructor();

        try {
            constructor.setAccessible(true);
            Object secret = constructor.newInstance();

            Field field = secretType.getDeclaredField("code");
            field.setAccessible(true);

            System.out.println("Secret: " + field.get(secret));
        } catch (InaccessibleObjectException exception) {
            System.out.println("Deep reflection BLOCKED");
        }
    }
}
~~~

**Step-by-step explanation:**

1. The import **demo.model.api.Greeting** and call Greeting.message() use **readability + exports**.
2. The client obtains **Class<?>** using the fully qualified name of Secret, without importing Secret.
3. **getDeclaredConstructor()** retrieves the constructor descriptor, without granting access.
4. **constructor.setAccessible(true)** requests deep reflection permission into a class of an unopened package.
5. If the module keeps the package closed, JPMS rejects the setAccessible operation with InaccessibleObjectException and the program prints the handled message.
6. If the package is opened to demo.consumer, enabling access and reading the private field can succeed.

### 7.2. Compile and run without opens

From the directory containing **src**, run:

~~~bash
javac -d out --module-source-path src -m demo.model,demo.consumer
java --module-path out -m demo.consumer/demo.consumer.Main
~~~

**Expected standard output on JDK 17+:**

~~~text
Public API OK
Deep reflection BLOCKED
~~~

With the source code above, the compiler still succeeds: the client does not import the internal type; internal package info is only looked up by name at runtime. The missing opens is detected at the **setAccessible(true) call at runtime**.

If try/catch is removed, InaccessibleObjectException propagates with a stack trace stating that module demo.model does not open package demo.model.internal to demo.consumer. This is **not a missing requires error**, nor does it mean Java could not find the class file.

### 7.3. Open the right package to the right module

Modify only the descriptor of **demo.model** to:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

Recompile and run again:

~~~bash
javac -d out --module-source-path src -m demo.model,demo.consumer
java --module-path out -m demo.consumer/demo.consumer.Main
~~~

**Expected standard output:**

~~~text
Public API OK
Secret: vault-42
~~~

Declaring **opens demo.model.internal to demo.consumer** allows module demo.consumer to perform deep reflection at runtime. Methods and fields remain private under normal Java rules; **you cannot write secret.code** directly in client code.

**Note on the code:** This is a complete program and you can create the exact files to run it; the two versions of module-info.java are **two mutually exclusive runs**, do not place both module descriptors at the same time. Swap the descriptor and recompile to observe the effect.

### 7.4. Using command-line arguments instead of editing the descriptor

If you want to keep demo.model's module-info.java in a state that **only exports the API**, you can grant open permission at launch time for diagnostics or legacy library support:

~~~bash
java --add-opens demo.model/demo.model.internal=demo.consumer --module-path out -m demo.consumer/demo.consumer.Main
~~~

This command opens package **demo.model.internal** of module **demo.model** to module **demo.consumer** at runtime. When running from an artifact previously compiled without opens, the output becomes:

~~~text
Public API OK
Secret: vault-42
~~~

The **--add-opens** option does not edit the source descriptor and does not make the package exported at **compile time**. Therefore, a direct call to Secret in the client still cannot be compiled solely via the run command above.

**Safe practice:** Prefer declaring required reflection permissions with clearly scoped opens if you own the module source code. Use **--add-opens** only when control is needed during deployment/migration or when a library's descriptor cannot be modified.

## 8. Proving That opens Does Not Replace exports

Suppose module demo.model keeps:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

The client tries adding a direct import:

~~~java
// Illustrating an invalid import in demo.consumer:
import demo.model.internal.Secret;
~~~

This snippet is **not a complete source file**; it illustrates an import that javac will reject because demo.model.internal **is not exported**. The compiler may report that the package is declared in module demo.model yet is not visible/exported to module demo.consumer.

To let the compiler allow client code to use **public Secret** directly, **exports demo.model.internal** (or a qualified export to demo.consumer) is required, alongside appropriate requires. However, that is rarely the desired design: internal Secret is not necessarily a stable API when a framework only needs reflection.

Even if the descriptor is changed to:

~~~java
module demo.model {
    exports demo.model.api;
    exports demo.model.internal;
}
~~~

accessing **private field code** via setAccessible from another module **is still blocked** unless the package is opened. Simply substituting **exports** does not solve the deep reflection use case.

From this:

- **Import error not seeing a package:** check requires and exports.
- **setAccessible rejected error:** check opens, caller module, and requested access type.
- **Class name does not exist error:** check module resolution, module path, class loader, package, and class name.
- **Member does not exist error:** check method/constructor/field signature; opening a package does not create missing members.

## 9. open module vs. Opening a Single Package

If a module has multiple packages needing reflection, Java supports the syntax:

~~~java
open module demo.model {
    exports demo.model.api;
}
~~~

This is an **open module**: every package in the module is opened for deep reflection at runtime, even if not exported. Nevertheless, compile-time direct access from other modules is still permitted only for packages that have been properly exported.

**Do not treat open module as equivalent to exporting all packages.** It changes reflection permissions, without exposing every implementation type as a compile-time API.

When a module uses multiple frameworks needing access to non-public members, open module can be convenient for testing or migration environments. However, it opens too broadly if only one package actually requires reflection. In library design, one typically chooses:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.entity to example.orm;
}
~~~

This is **illustrative code**: example.orm must be replaced with the framework's actual module name in the system. Do not copy a nonexistent module name into an application and expect it to automatically pull dependencies.

**Technical note:** Inside an **open module** declaration, do not combine individual opens directives as in a normal module; an open module already opens all packages. If per-package or per-caller-module control is needed, use a normal module with qualified opens.

## 10. Qualified opens and Permission Scope

There are two forms:

~~~java
opens demo.model.internal;
~~~

and:

~~~java
opens demo.model.internal to demo.consumer;
~~~

The first form opens to **all modules**. The second opens only to **demo.consumer**. This matters when multiple frameworks run together:

- If a mapper module needs to read entity fields, open the exact entity package to the **mapper's real module name**.
- If another serialization library needs separate reflection, you must also open to that library's module or configure an appropriate solution.
- A program run from the classpath typically resides in the **unnamed module**. When using command-line options, target **ALL-UNNAMED** opens to all unnamed modules, for example the illustrative syntax:

~~~bash
java --add-opens demo.model/demo.model.internal=ALL-UNNAMED -cp app.jar app.Main
~~~

This is merely a **syntax illustration**. For the command to actually run, you must also ensure module demo.model is found/resolved in the launch configuration; **-cp app.jar** alone does not prove demo.model has been resolved. Use a specific named module in configuration when possible, as ALL-UNNAMED grants broader permission.

**Qualified opens does not mean the caller module must write requires for reflection to work in every circumstance**, yet the module containing the class must still be resolved and visible to the class loader. In normal modular programs, a requires dependency is a clear way to ensure the needed module is resolved. When using dynamic reflection and modules lack explicit readability, verify actual module resolution/loader behavior rather than inferring from imports.

## 11. How Do --add-exports and --add-opens Differ?

JDK tools provide options to adjust package boundaries when module descriptors cannot yet be edited. The two options are not equivalent.

| Option | Purpose | When it matters |
| --- | --- | --- |
| **--add-exports source.module/pkg=target.module** | Allows target module to access public types/members in a package not normally exported | Compile and/or runtime when using internal APIs in the ordinary Java way |
| **--add-opens source.module/pkg=target.module** | Grants target module deep reflection into the package | Runtime, when reflection needs to bypass Java access checks |
| **--add-reads source.module=target.module** | Adds module readability relation when the module graph needs adjustment | Compile or runtime depending on tool and scenario |

Example:

~~~bash
java --add-exports demo.model/demo.model.internal=demo.consumer --module-path out -m demo.consumer/demo.consumer.Main
~~~

The **--add-exports** option at runtime only adds an export for the package's public API to the target; it **does not** allow the caller to enable accessibility on Secret's private field. If Main still needs the private field, the package must be opened with **--add-opens**, not just add-exports.

When compiling source that directly uses an internal API, add-exports options may need to be configured **on both javac and java** respectively. Adding an override only at runtime does not turn a previous import error into compilable source.

**Note:** these options create exceptions to strong encapsulation and increase dependency on implementations not published as stable public APIs. They suit intentional transitions or diagnostics and should be documented in build/deployment. Do not solve every access permission error by opening all JDK packages.

## 12. Reflection API: Actual Permissions Depend on Access Method

Some familiar APIs:

| API or action | Points to note |
| --- | --- |
| **Class.forName(name)** | Loads/resolves class via appropriate class loader; does not grant access to constructors/fields |
| **getMethod(...)** | Finds public method matching name/signature; invoking still undergoes access checks |
| **getDeclaredMethod(...)** | Finds directly declared method including private; getting a Method object does not permit invoke if permission is lacking |
| **getConstructor(...)** | Finds public constructor; does not bypass module access checks |
| **getDeclaredConstructor(...)** | Retrieves directly declared constructor including non-public |
| **getField(...) / getDeclaredField(...)** | Retrieves public/inherited field or directly declared field |
| **setAccessible(true)** | Requests suppressing Java language access checks; requires JPMS conditions to permit |
| **trySetAccessible()** | Attempts to enable accessible; may return false if permission is insufficient |
| **Method.invoke / Constructor.newInstance / Field.get** | Executes/accesses; still depends on permissions, target object, and signature |

**Common misconceptions:**

- Obtaining a **Field** via getDeclaredField does not prove a private field can be read.
- A **public class** in an unexported package still does not become a compile-time API for other modules.
- Reflection on a **public method of an exported public type** can succeed without opens; not all reflection is deep reflection.
- Reading public annotation metadata does not imply permission to modify private fields.
- Opening a package does not guarantee reflection APIs will not fail due to null objects, wrong constructor arguments, invocation exceptions, or incompatible values.

### 12.1. InaccessibleObjectException and IllegalAccessException

When code **attempts to enable setAccessible(true)** to cross an unopened module boundary, Java typically throws **InaccessibleObjectException** right on the enable-access call.

When code **does not enable accessible**, yet calls a constructor/method/field that is inaccessible under ordinary rules, the reflection API may throw **IllegalAccessException**.

Both relate to permissions, yet their locations and causes differ. Do not catch one exception and assume all remaining errors are due to opens.

### 12.2. Why does Java 17+ expose this error more easily?

During transitional releases in JDK 9–16, the JVM permitted some illegal reflective access with warnings to support legacy apps. Starting in **JDK 17**, strong encapsulation is enforced more strictly by default for many JDK internals (JEP 403). Consequently, an older framework calling setAccessible on java.base internals may hit InaccessibleObjectException upon upgrading JDK.

The preferred solution is updating the framework/library or switching to supported APIs. If unable to migrate immediately, use narrowly scoped **--add-opens** and document the reason. The legacy **--illegal-access** option is no longer a way to broadly re-enable reflective access as before on JDK 17+.

## 13. When Configuring Frameworks in Real Projects

Suppose there is **domain.entity.Customer** with private fields, and an ORM/serializer framework needs to instantiate or populate state via reflection.

An illustrative module descriptor can be used:

~~~java
module example.application {
    requires example.orm;
    exports example.application.api;

    opens example.application.entity to example.orm;
}
~~~

This is **illustrative syntax**: example.orm and the packages must be replaced with the actual framework module/package names. Do not assume all ORMs work the same way; some frameworks use public constructors, bytecode enhancement, MethodHandles, annotation processing, or code generation and have different configuration requirements.

To decide between exports and opens:

1. **Does the framework or another module need to import/call public APIs of this package?** If yes, consider exports to the right client.
2. **Does the framework use reflection to touch non-public members at runtime?** If yes, consider opens on the package to the framework module.
3. **Can a public API or adapter be designed to avoid deep reflection?** If yes, that may be a lower-privilege option.
4. **Does the framework module have a stable name?** Verify the module name when using qualified opens. For libraries running on the classpath/unnamed module, configuration may differ.
5. **Does the whole package need opening?** JPMS opens is declared per package, not per individual field. Package design should avoid mixing sensitive data with types the framework must reflect upon.
6. **Is compatibility required across JVM/IDE/test runner and production runtime?** Test on the actual module path rather than relying on tests running from the classpath.

Do not add **open module** just because one model package needs mapping. Qualified opens or dedicated public APIs usually keep boundaries clearer.

## 14. How to Diagnose Errors by Phase

| Symptom | Time | What to check first |
| --- | --- | --- |
| **package ... is not visible** | Compile | requires, exports (and qualified export target), module path |
| **module not found** | Compile or runtime module resolution | Module path, module name, descriptor, dependencies |
| **cannot find symbol** | Compile | Imports/type name, compile classpath/module path, member signature |
| **IllegalAccessError** | Runtime linkage | Possibly due to changed exports/module visibility or binary incompatibility |
| **ClassNotFoundException** | Runtime | Class name, class loader, whether module was resolved |
| **IllegalAccessException** | Runtime reflection | Normal access permissions when invoking constructor/method/field |
| **InaccessibleObjectException** | Runtime reflection | setAccessible rejected: check opens and caller module |
| **NoSuchFieldException/NoSuchMethodException** | Runtime reflection | Member name, signature, declared/public API; opens does not create members |
| **InvocationTargetException** | Runtime reflection | Exception actually thrown by the method/constructor; read cause |

A typical scenario:

~~~text
At compile time: importing public API succeeds
    |
    v
At runtime: Class.forName finds the implementation class
    |
    v
getDeclaredField finds the private field
    |
    v
setAccessible(true) throws InaccessibleObjectException
    |
    v
Add opens for the right package to the right caller
~~~

Conversely, if the compiler forbids importing the class in the first place, merely adding opens does not cure the compile-time error. When an error comes from a library absent from the module path or an unresolved module, fix dependency/module resolution first.

### 14.1. Inspecting module descriptors and module path

Useful commands:

~~~bash
java --module-path out --describe-module demo.model
~~~

The command displays loaded module descriptor details such as requires and exports/opens. Output line formatting depends on the JDK and active descriptor, so no fixed stdout is hardcoded.

~~~bash
java --show-module-resolution --module-path out -m demo.consumer/demo.consumer.Main
~~~

The command helps observe modules resolved at launch. If runtime still fails to find the module, verify the out directory tree, module names, and JAR packaging.

When using a JAR on the module path, you can view its descriptor with **jar --describe-module --file path/to/library.jar** if the JAR has valid module metadata.

## 15. Practical Rules and Security Notes

**exports is an API publishing decision.** Broadening exports can cause other applications to start depending on implementation classes; revoking an export later can break compatibility. Export only packages genuinely designed as API.

**opens is a reflection-granting decision.** A library permitted to read/write private fields can bypass many class-level encapsulation invariants. Open only necessary packages to the exact modules requiring them. Use **ALL-UNNAMED** or open module only when fully understanding the scope of impact.

**Neither replaces testing.** Runtime configurations differing from compile configurations can cause errors that surface only in production. With JDK 17+, test using the same launch mode (classpath or module path), same module names, and same launcher options.

**Limiting access is part of architectural design.** API packages serve use cases guaranteed to be stable; internal packages are for implementation only and may be opened very narrowly to frameworks if mandatory.

**Do not confuse library configuration with unconditional permission.** JPMS unlocks reflection capabilities per package/module, yet code remains subject to reflection API rules, class loaders, operation validity, and other system safeguards.

## 16. Practice Exercises

### Exercise 1: Choosing directives

You have module **sales.model** with package **sales.model.api** containing public DTOs for other applications, and package **sales.model.entity** containing private fields that a serializer in module **json.mapper** needs to access.

Write the corresponding module-info.java: export the API; open entity only to json.mapper; require what is necessary based on the module's actual dependencies. Explain why entity does not need to be exported if clients do not import classes from that package.

### Exercise 2: Changing permissions step by step

Using the demo.model and demo.consumer example in section 7:

1. Run with only exports API.
2. Add **opens demo.model.internal to demo.consumer** and rerun.
3. Try removing opens and only **exports demo.model.internal**; observe reading the private field.
4. Try keeping the original descriptor and adding **--add-opens** at launch.

Record the stdout and cause of each change.

### Exercise 3: Distinguishing errors

With a public class in an unexported package, the client attempts to import the class: is the error at compile time or runtime? If replacing the import with Class.forName and calling setAccessible on the constructor, which phase can the error shift to? What changes when the package gets a qualified opens?

### Exercise 4: Distinguishing reflection APIs

Given a Class object of a class with a private field, explain the difference between:

- **getField("secret")** and **getDeclaredField("secret")**.
- **field.get(instance)** and **field.setAccessible(true); field.get(instance)**.
- **field.trySetAccessible() == false** and a successful reflection operation.

A non-public member may be found in metadata yet not necessarily permitted for use.

### Exercise 5: Auditing module descriptors

In a modularized application, inspect every **exports**, **opens**, and **--add-opens**. For each entry, identify who uses that permission, whether the use case is compile-time API or runtime reflection, whether scope can be narrowed with **to module.name**, and whether it has been tested on the actual runtime JDK version.

## 17. Self-Check Questions

- Why can a public class in a named module still fail to be imported from another module?
- What problem does **requires** solve, and what problem does **exports** solve?
- Does an exported package allow another module to read a private field via reflection?
- Does **opens** make importing a class in an unexported package permitted at compile time?
- Why does Class.forName succeeding not mean Constructor.newInstance is permitted?
- What is the difference between **setAccessible(true)** and **trySetAccessible()**?
- When should **qualified opens** be used instead of open module?
- Does **--add-exports** substitute for **--add-opens** when a private field is needed?
- For a program on the classpath, what does **ALL-UNNAMED** mean?
- In a stack trace, what sign suggests missing opens rather than a missing dependency?
- Why should frameworks be updated rather than opening access to JDK internals indefinitely?

## 18. Official References

- **Java Language Specification 21, §7.7.2 – Exported and Opened Packages:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2
- **Dev.java – Reflective Access with Open Modules and Open Packages:** https://dev.java/learn/organizing/modules/opening-for-reflection/
- **Dev.java – Qualified exports and opens:** https://dev.java/learn/organizing/modules/qualified-exports-opens/
- **Dev.java – Circumventing Strong Encapsulation with --add-exports and --add-opens:** https://dev.java/learn/organizing/modules/add-exports-opens/
- **Oracle Java SE 21, AccessibleObject API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **Oracle Java 21, java launcher options:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **OpenJDK JEP 403 – Strongly Encapsulate JDK Internals:** https://openjdk.org/jeps/403

**Remember:** For **Java code calling public APIs**, use module readability and properly scoped **exports**. For **frameworks needing deep reflection into non-public members**, use **opens** for the right package and caller module. **exports publishes an API for normal access; opens grants reflective access at runtime.**