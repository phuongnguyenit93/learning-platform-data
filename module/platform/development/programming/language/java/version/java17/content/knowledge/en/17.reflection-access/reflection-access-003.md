# Accessing Public Members Across Module Boundaries in Java 17

In Java, declaring a class or method `public` is not enough for every module to use it. Since the Java Platform Module System (JPMS) was introduced in Java 9, cross-module accessibility also depends on **whether the package is exported** and whether the consuming module declares the appropriate dependency relationship.

This also applies when using Reflection. A method with the `public` modifier that resides in a package not exported to the calling module may still fail to be invoked via `Method.invoke`. Reflection allows looking up members from class metadata, but **finding a member does not mean having permission to access that member**.

This lesson explains how public member access works across module boundaries in Java 17, how to declare `exports`, `requires`, and qualified exports, how Reflection checks access permissions, and the difference between `exports` and `opens`.

## 1. Four conditions to distinguish

Suppose module `com.example.library` provides a class:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

An application module wanting to call `greet` needs to consider the following factors:

1. **The declared type must be accessible:** the class `GreetingService` is `public`.
2. **The member must be accessible:** the method `greet` is `public`.
3. **The package must be exported by the providing module:** the library module must export the package `com.example.api` to the application module.
4. **The consuming module must declare the proper dependency:** in normal Java code, the application module declares `requires com.example.library`.

If the export condition is missing, having `public` on both the class and the method still does not allow another module to access them in ordinary source code.

Keep in mind:

~~~text
Module A (library)
    |
    | exports com.example.api
    v
Package com.example.api
    |
    +-- public class GreetingService
            |
            +-- public method greet(...)

Module B (application)
    |
    +-- requires com.example.library
    |
    +-- can use GreetingService.greet(...)
~~~

**Module boundaries are enforced at the package level.** The `exports` directive exports a package, not an individual method or a single class.

## 2. Declaring modules and exporting packages

An application using the module path typically has this layout:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── com/example/api/GreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 2.1. The module providing the API

File `src/com.example.library/module-info.java`:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

The directive:

~~~java
exports com.example.api;
~~~

means the package `com.example.api` is exported to other modules. `public` types and `public` members of those types can be read and used by modules according to Java access rules.

File `src/com.example.library/com/example/api/GreetingService.java`:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 2.2. The module consuming the API

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

The `requires` directive declares that the application module depends on the library module. As a result, source code in `com.example.app` can reference public types belonging to exported packages from the library.

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("An"));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --module-source-path src -d out -m com.example.library,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello, An
~~~

In this example, three parts work together:

- `exports com.example.api` in the library module publishes the API package.
- `requires com.example.library` in the application module declares the dependency.
- The `public` modifier on the class and method allows using them from another package, once the module boundary permits it.

### 2.3. What happens if exports is omitted?

If the library module only declares:

~~~java
module com.example.library {
    // Does not export com.example.api
}
~~~

then the application code:

~~~java
import com.example.api.GreetingService;
~~~

cannot compile across the module boundary. The compiler reports that the package is not exported or is not visible to the consuming module.

Adding `public` to the class or method does not fix the issue. You must adjust the module contract with the appropriate `exports` directive.

## 3. Unqualified export and qualified export

Not every API package needs to be published to all modules. Java supports **qualified exports**, which export a package only to one or a specified group of modules.

### 3.1. Exporting to all modules that read the library

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

This is an unqualified export. The package is exported to any module that can read the library module.

### 3.2. Exporting only to selected modules

~~~java
module com.example.library {
    exports com.example.api to com.example.app;
}
~~~

In this case, the package `com.example.api` is exported only to the module `com.example.app`. Other modules do not automatically gain access to that package.

Multiple modules can be specified:

~~~java
module com.example.library {
    exports com.example.api
            to com.example.app, com.example.integration;
}
~~~

The names after `to` are **module names**, not package names or class names.

### 3.3. When to use qualified exports?

Qualified exports are useful when a library wants to expose part of its API only to known collaborating modules, for example:

- An SPI package dedicated to an internal plugin module.
- An integration package used only among modules within the same product.
- Support APIs exposed to a specific adapter module.
- Keeping implementation packages encapsulated from the rest of the application.

Do not use qualified exports as a substitute for a public API that needs to be consumed by many applications. If a package is the library's public contract, an unqualified export is usually clearer.

## 4. Exporting a package does not export every member

The `exports` directive opens module access for a package, but Java access modifier rules still apply.

~~~java
package com.example.api;

public class Account {
    public String id() {
        return "A-100";
    }

    protected void refresh() {
    }

    void internalCheck() {
    }

    private void resetSecret() {
    }
}
~~~

If the package `com.example.api` is exported:

| Member | Modifier | Accessible from another module in normal source code? |
|---|---|---|
| `id()` | `public` | Yes |
| `refresh()` | `protected` | According to protected rules: requires inheritance and valid access conditions |
| `internalCheck()` | package-private | No |
| `resetSecret()` | `private` | No |

`exports` does not turn every member into `public`. It allows other modules to reach public types in the package and use members according to standard Java modifiers, inheritance rules, and access rules.

A top-level package-private type still does not become public just because its package is exported.

### 4.1. Public members of a non-public class

Example:

~~~java
package com.example.api;

class InternalService {
    public void execute() {
    }
}
~~~

Even though `execute` is `public`, the class `InternalService` is not public, so source code in another package cannot directly reference this class.

To expose an API to another module, you need a declared type with the appropriate access level, typically a public class/interface/record and public members in an exported package.

## 5. Module readability: the role of requires

In module source code, `requires` declares that the current module needs to read another module.

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

If this directive is omitted, the compiler does not treat the library module as a declared dependency of the application during normal modular compilation.

### 5.1. requires does not replace exports

The two directives address two different sides:

| Directive | Where is it placed? | Meaning |
|---|---|---|
| `requires com.example.library;` | Consuming module | Declares that the current module depends on the library module |
| `exports com.example.api;` | Providing module | Publishes the package to other modules |
| `exports com.example.api to com.example.app;` | Providing module | Publishes the package to the specified module |

Having `requires` alone when the package is not exported still does not allow the application to access that package in normal source code.

Having `exports` alone without the application declaring the appropriate dependency leaves the application's module configuration incomplete.

### 5.2. requires transitive

A module can publish an API whose signatures contain types from a dependent module. In that case, `requires transitive` allows modules that read the current module to also read the propagated dependency:

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

For example, the public API of `com.example.api` might return the type `com.example.model.User`. A module consuming the API needs to read both the API module and the model module to use types appearing in public signatures.

Do not use `requires transitive` just to "open up" access to a package. It handles transitive readability relationships, while package accessibility is still governed by exports and access modifiers.

## 6. Accessing public members via Reflection

Reflection allows a program to look up and invoke members based on a `Class` object at runtime. However, Reflection does not bypass module boundaries.

Example with a library module exporting `com.example.api`:

~~~java
package com.example.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

The application module can invoke it via Reflection:

~~~java
package com.example.app;

import java.lang.reflect.Method;

public class ReflectiveMain {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName("com.example.api.GreetingService");

        Object service = type.getConstructor().newInstance();

        Method method = type.getMethod("greet", String.class);
        Object result = method.invoke(service, "An");

        System.out.println(result);
    }
}
~~~

Because the class and method are both public and the package is exported to the calling module, this reflective operation is permitted.

### 6.1. getMethod and getDeclaredMethod

Two common APIs:

~~~java
Method publicMethod = type.getMethod("greet", String.class);
Method declaredMethod = type.getDeclaredMethod("greet", String.class);
~~~

- `getMethod` finds public methods of the class, including inherited public methods.
- `getDeclaredMethod` finds methods declared directly in the class, not limited to public; it can find private, protected, or package-private methods.

**Discoverability is different from invokability.** A method may be found via Reflection, yet when invoked, the access check can still reject it.

Example:

~~~java
Method method = type.getDeclaredMethod("internalOperation");
method.invoke(instance); // May fail if the caller does not have access permission.
~~~

Do not use `getDeclaredMethod` as an automatic way to bypass module encapsulation.

### 6.2. Public members in an unexported package

Suppose the library module has:

~~~java
module com.example.library {
    exports com.example.api;
    // Does not export com.example.internal
}
~~~

and class:

~~~java
package com.example.internal;

public class InternalDiagnostics {
    public String status() {
        return "internal";
    }
}
~~~

Both the class and the method are public, but package `com.example.internal` is not exported to the application module. Other modules may hit restrictions when trying to reflectively access the member.

Test code example:

The library module could provide a public factory in an exported package to construct an internal object without exposing the implementation type:

~~~java
package com.example.api;

public class DiagnosticsFactory {
    public Object create() {
        return new com.example.internal.InternalDiagnostics();
    }
}
~~~

The application module receives the object as `Object`, then looks up the public method:

~~~java
import com.example.api.DiagnosticsFactory;

Object instance = new DiagnosticsFactory().create();
Method method = instance.getClass().getMethod("status");

System.out.println(method.invoke(instance));
~~~

Obtaining the object and the `Method` does not make the internal package exported. The `invoke` call can still throw `IllegalAccessException` because the method is declared in a class belonging to a package not exported to the caller.

Being able to load class metadata or obtain a `Method` object does not guarantee `invoke` is allowed. If the package is not exported or opened to the caller appropriately, the access operation can throw `IllegalAccessException`.

The right fix depends on the design intent:

- If this is a public API for application modules, export the appropriate package.
- If this is an internal detail that only requires deep Reflection for a specific framework/module, consider qualified `opens`.
- If the package is not intended for external use, do not rely on accessing it via Reflection.

## 7. exports and opens: two different mechanisms

This is the most important distinction when working with Reflection in the module system.

| Directive | Normal source access | Reflection on public members | Deep reflection into non-public members |
|---|---|---|---|
| `exports p` | Yes, per access modifiers | Yes | Not automatically |
| `exports p to m` | Yes, only specified module | Yes, only specified module | Not automatically |
| `opens p` | Does not grant normal source access | Can enable access override via `trySetAccessible` when needed | Can allow deep reflection |
| `opens p to m` | Does not grant normal source access | Module `m` can enable access override when needed | Can allow deep reflection for `m` |

### 7.1. exports is for public APIs

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Use when other modules need to:

- Import and reference public classes/interfaces/records.
- Call public constructors and methods.
- Access public fields per Java rules.
- Use Reflection on public members of public types in the exported package.

This is the proper way to publish a library's public API.

### 7.2. opens is for runtime Reflection

~~~java
module com.example.library {
    opens com.example.internal;
}
~~~

`opens` does not allow other modules to import that package in Java source code as an exported package. It allows runtime Reflection to reach types and members in the package, including deep reflection according to JPMS rules.

A framework may need to read or write private fields to map objects. In that situation, `opens` may be a more appropriate directive than `exports`.

### 7.3. Qualified opens

If only one framework module needs deep reflection:

~~~java
module com.example.library {
    exports com.example.api;
    opens com.example.model to com.example.mapper;
}
~~~

In this example:

- `com.example.api` is the public API for consuming modules.
- `com.example.model` is opened to the `com.example.mapper` module for runtime Reflection.
- Other modules do not automatically gain deep reflection access to `com.example.model`.

Qualified opens helps limit the internal access surface.

### 7.4. Open module

Java allows declaring:

~~~java
open module com.example.library {
    requires com.example.model;
}
~~~

An `open module` opens all packages of the module for runtime Reflection. However, that **does not mean all packages are exported for normal source access**.

This is a broad choice. In module design, prefer opening only the required packages to the required modules using qualified `opens` whenever possible.

## 8. Controlling deep reflection with trySetAccessible

From Java 9 onward, the `trySetAccessible` API attempts to enable bypassing access checks for a member. It returns a boolean indicating whether enabling it succeeded.

Example:

~~~java
import java.lang.reflect.Field;

Field field = type.getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(instance);
    System.out.println(value);
} else {
    System.out.println("The module does not open the package for deep reflection");
}
~~~

If the package is open to the calling module, the operation can succeed subject to JPMS conditions. If the package is not open and no other exception applies, the method returns `false`.

### 8.1. setAccessible(true) can fail

The older approach:

~~~java
field.setAccessible(true);
~~~

can throw `InaccessibleObjectException` when access cannot be opened. Therefore, for code that needs controlled error handling, `trySetAccessible` often provides cleaner handling.

Do not assume calling `setAccessible(true)` always crosses module boundaries. Strong encapsulation in JPMS is intentionally enforced to protect internal APIs and implementations.

### 8.2. canAccess to check current accessibility

`AccessibleObject.canAccess(Object)` checks current accessibility to a member:

~~~java
Method method = type.getMethod("greet", String.class);

boolean accessible = method.canAccess(instance);
System.out.println(accessible);
~~~

For instance members, pass the target object. For static members, pass `null`.

`canAccess` does not modify access permissions. `trySetAccessible` is the method that attempts to enable bypassing access checks where allowed by the module system.

## 9. Complete example: exporting an API and opening a model package

Suppose there are three modules:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   ├── com/example/api/UserService.java
│   └── com/example/model/UserRecord.java
├── com.example.mapper/
│   ├── module-info.java
│   └── com/example/mapper/MapperMain.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Library module:

~~~java
module com.example.library {
    exports com.example.api;
    exports com.example.model;
    opens com.example.model to com.example.mapper;
}
~~~

Public API:

~~~java
package com.example.api;

import com.example.model.UserRecord;

public class UserService {
    public UserRecord findUser() {
        return new UserRecord("U01", "An");
    }
}
~~~

Model:

~~~java
package com.example.model;

public class UserRecord {
    private final String id;
    private String name;

    public UserRecord(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Mapper module:

~~~java
module com.example.mapper {
    requires com.example.library;
}
~~~

Reflection code in the mapper:

~~~java
package com.example.mapper;

import com.example.api.UserService;

import java.lang.reflect.Field;

public class MapperMain {
    public static void main(String[] args) throws Exception {
        Object user = new UserService().findUser();

        Field nameField = user.getClass().getDeclaredField("name");

        if (nameField.trySetAccessible()) {
            System.out.println(nameField.get(user));
        } else {
            System.out.println("Access was not opened");
        }
    }
}
~~~

Package `com.example.model` is also exported because the type `UserRecord` appears in the public signature of `UserService`. Thus modules reading the library can use `UserRecord`'s public API. At the same time, this package is opened only to the mapper, so the mapper can perform deep reflection on private fields; the app module does not receive that deep access.

Regular application module:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Code in app can call `UserService` and use `UserRecord`'s public API because both packages are exported. However, app is not granted deep reflection access to package `com.example.model` by default, since that package is opened only to `com.example.mapper`.

This allows the library to publish a stable API while opening the model portion only to the designated framework.

## 10. Qualified export and qualified opens in practice

Look at the library module:

~~~java
module com.example.library {
    exports com.example.api to com.example.app, com.example.integration;
    opens com.example.model to com.example.mapper;
}
~~~

This can be read as:

- Modules `com.example.app` and `com.example.integration` can access the public API in `com.example.api`.
- Module `com.example.mapper` can use deep Reflection in `com.example.model`.
- Other modules do not gain those permissions merely because they can read the library module.

This follows the principle of **least privilege**: only expose packages and open Reflection to the modules that genuinely need the permission.

When a framework reports a Reflection error, do not immediately open the entire module. First identify:

1. Which package is the framework accessing?
2. What is the framework's module name?
3. Does it need to call a public API or access private fields/methods?
4. Does the package need `exports` or `opens`?
5. Can the directive be restricted with qualified export/open?

## 11. Easily confused cases

### 11.1. Public class in an unexported package

~~~java
package com.example.internal;

public class InternalApi {
    public void execute() {
    }
}
~~~

If `com.example.internal` is not exported, other modules cannot reference this class in normal source code. The `public` modifier does not cross module boundaries.

### 11.2. Exported package, but private members remain private

~~~java
package com.example.api;

public class User {
    private String password;
}
~~~

`exports com.example.api` lets other modules use the package's public API. It does not automatically allow reading `password` via deep reflection. For a framework to access private members, the package must be opened to the framework module, or an explicit accessor API must be designed.

### 11.3. Opened package, but not exported

~~~java
module com.example.library {
    opens com.example.model to com.example.mapper;
}
~~~

The mapper module can use Reflection within the opened scope, but mapper source code cannot import types from `com.example.model` based solely on the `opens` directive. If the mapper needs to use those types in source signatures, the package must also be exported to the mapper.

### 11.4. getDeclaredMethod does not bypass access checks

~~~java
Method method = type.getDeclaredMethod("secretOperation");
~~~

This statement can find a private method, but calling `method.invoke(...)` is still subject to access rules. If the package is not appropriately opened, deep Reflection is denied.

### 11.5. HTTP status or I/O errors unrelated to module access

If `Method.invoke` throws `InvocationTargetException`, distinguish:

- `IllegalAccessException`: the caller is not permitted to access the method.
- `InvocationTargetException`: the method was invoked, but code inside the method threw an exception.
- `InaccessibleObjectException`: the access override could not be enabled via the Reflection API.
- `ClassNotFoundException`: the requested class name could not be found.

Reading the exception type accurately separates module/access issues from logic errors inside the invoked method.

### 11.6. Do not confuse classpath with module path

Code running on the classpath typically belongs to the unnamed module. The unnamed module has different access rules than named modules in a modular application. Therefore, a program that runs on the classpath does not prove that the `exports`/`opens` configuration among named modules is correct.

When you want to verify JPMS boundaries, compile and run the modules on the module path as shown in the examples.

## 12. Intentional Reflection error handling

When invoking a method via Reflection, handle the key error groups separately:

~~~java
try {
    Method method = type.getMethod("greet", String.class);
    Object result = method.invoke(instance, "An");
    System.out.println(result);

} catch (NoSuchMethodException e) {
    System.err.println("API does not have the expected method");

} catch (IllegalAccessException e) {
    System.err.println("No permission to access method across module boundary");

} catch (InvocationTargetException e) {
    System.err.println("Method threw an internal error: "
            + e.getCause());
}
~~~

If deep reflection is required:

~~~java
Field field = type.getDeclaredField("secret");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package has not been opened to the current module"
    );
}
~~~

Do not catch all exceptions and continue as if access succeeded. When a module boundary denies access, address it in module configuration or change the API design.

## 13. Inspecting module state at runtime

`Module` APIs help observe export/open configuration:

~~~java
Module targetModule = GreetingService.class.getModule();
Module callerModule = Main.class.getModule();

System.out.println(targetModule.getName());

boolean exported = targetModule.isExported(
        "com.example.api",
        callerModule
);

boolean opened = targetModule.isOpen(
        "com.example.api",
        callerModule
);

System.out.println("Exported: " + exported);
System.out.println("Opened: " + opened);
~~~

- `isExported(packageName, otherModule)` checks whether the package is exported to the target module.
- `isOpen(packageName, otherModule)` checks whether the package is opened for Reflection to the target module.

These are module-state observation APIs. They are useful when debugging complex module configurations or framework Reflection errors.

Do not use the result of `isOpen` to infer that source code can import the package; `opens` and `exports` serve different purposes.

## 14. API design choices

When designing a modular library, identify which packages truly form the public API:

| Goal | Suitable design |
|---|---|
| Other modules import and call public API | `exports` the API package |
| Only selected modules may use the API package | Qualified `exports` |
| A framework needs access to private fields/methods | Qualified `opens` for the model package |
| The package is an implementation detail | Do not export the package |
| Multiple packages need internal Reflection without opening the entire module | Open each necessary package individually |
| Other modules must read types appearing in public APIs | Declare appropriate `requires`; use `requires transitive` if the dependency must propagate |
| Want to verify real module boundaries | Run on the module path, not only the classpath |

A good API exposes the types users need to reference, keeps implementation packages encapsulated, and opens deep reflection only when a framework has a specific reason.

### 14.1. Do not use Reflection to work around API design

If another module frequently needs to read private fields or call private methods, the API may simply be missing an appropriate public operation.

For example, instead of opening an entire model so a framework can arbitrarily mutate fields, consider:

~~~java
public class User {
    private String displayName;

    public String displayName() {
        return displayName;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Invalid name");
        }
        this.displayName = newName;
    }
}
~~~

A public API preserves object invariants and lets the data-owning module control how changes occur.

## 15. Small example to self-verify access rules

Suppose library module:

~~~java
module demo.library {
    exports demo.api;
}
~~~

In package `demo.api`:

~~~java
package demo.api;

public class PublicService {
    public void run() {
        System.out.println("public API");
    }

    private void secret() {
        System.out.println("secret");
    }
}
~~~

In module app:

~~~java
module demo.app {
    requires demo.library;
}
~~~

App code:

~~~java
package demo.app;

import demo.api.PublicService;

public class Main {
    public static void main(String[] args) throws Exception {
        PublicService service = new PublicService();
        service.run();

        var method = PublicService.class.getDeclaredMethod("secret");

        System.out.println(method.trySetAccessible());
    }
}
~~~

Results:

- `service.run()` runs normally because the class and method are public in an exported package.
- `trySetAccessible()` for the private method may return `false` because the package is not opened to the app module.
- If deep reflection is needed, the library module can add `opens demo.api to demo.app;`, though that opens deep Reflection access to the app module and warrants design consideration.

Compile and run:

~~~bash
javac --module-source-path src -d out -m demo.library,demo.app
java --module-path out -m demo.app/demo.app.Main
~~~

## 16. Practice exercises

### Exercise 1: Why is a public method inaccessible?

Module `store.core` contains:

~~~java
package store.internal;

public class StorageEngine {
    public void start() {
    }
}
~~~

Module `store.app` declares `requires store.core`, but module core does not export `store.internal`.

**Question:** Why can't app import `StorageEngine`?

**Answer:** `requires` only declares dependency/readability. Package `store.internal` has not been exported from `store.core`. Export the package if it is a public API; if it is an implementation detail, app should not access it directly.

### Exercise 2: Choose exports or opens?

An application module needs to import and call public methods in `com.example.api`. Which directive should be chosen?

**Answer:** `exports com.example.api;`.

A mapper framework needs to access private fields in `com.example.model` at runtime. Which directive should be chosen?

**Answer:** `opens com.example.model to mapper.module.name;`, using the framework's actual module name.

### Exercise 3: Qualified export

Only module `com.example.admin` is allowed to use package `com.example.adminapi`. Write the module descriptor.

**Answer:**

~~~java
module com.example.platform {
    exports com.example.adminapi to com.example.admin;
}
~~~

### Exercise 4: Reflection finds it but cannot invoke it

`getDeclaredMethod("secret")` returns a `Method`. Why can `invoke` still throw `IllegalAccessException`?

**Answer:** Reflection lookup APIs do not grant access permission. Invocation is still subject to Java and JPMS access checks. The package must be appropriately exported/opened for the type of access; deep reflection also requires package-opening permission.

### Exercise 5: Does requires replace exports?

The app module already has `requires com.example.library`. Why can't it still use a public class in an unexported package?

**Answer:** `requires` establishes a dependency/readability relationship. `exports` is what publishes the package to other modules. The two directives address two different conditions.

### Exercise 6: Runtime module check

Use `Module.isExported` and `Module.isOpen` to check whether package `com.example.api` is exported/opened to the app module.

**Reference answer:**

~~~java
Module library = PublicService.class.getModule();
Module app = Main.class.getModule();

System.out.println(library.isExported("com.example.api", app));
System.out.println(library.isOpen("com.example.api", app));
~~~

## 17. Key takeaways

When accessing public members across module boundaries in Java 17, check in order:

1. Is the published class or interface public?
2. Is the member to be invoked public?
3. Has the package containing that type been exported to the caller by the providing module?
4. Has the consuming module declared the appropriate dependency/readability in the module graph?
5. If using Reflection, are you only calling public members or do you need deep reflection into private/package-private members?
6. If deep reflection is needed, has the package been opened to the right caller module?

**`exports` publishes an API; `opens` grants runtime Reflection access.** The two directives do not substitute for each other. When you only need to call a public API, exporting the right package is the proper design. When a framework genuinely needs deep access into implementation details, open the package selectively to that module.

## 18. References

- [Oracle Java SE 17 — Module Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): module declaration syntax, `requires`, `exports`, and `opens`.
- [Oracle Java SE 17 — Module API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): checking modules, package exports, and opens at runtime.
- [Oracle Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, and access override.
- [Oracle Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): finding and invoking methods via Reflection.
- [Oracle Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getMethod`, `getDeclaredMethod`, and class metadata.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS design, readability, exports, and opens.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): context for strong encapsulation of JDK internal implementations.
