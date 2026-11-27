# Distinguishing IllegalAccessError and InaccessibleObjectException in Java 17

**Topic:** Java 17  
**Chapter:** Modules and Strong Encapsulation  
**Lesson:** Distinguishing IllegalAccessError and InaccessibleObjectException

Since Java 9, the Java Platform Module System (JPMS) has added access boundaries between modules. A package can be publicly exported to other modules with `exports`, or opened for reflection with `opens`. These two mechanisms serve different kinds of access. When a program, library, or framework crosses an unauthorized module boundary, Java may report an error at linkage time or when reflection attempts to suppress access checks.

Two easily confused error names are:

- **`IllegalAccessError`**: a `LinkageError` that occurs when compiled code attempts to access a class, method, or field that the JVM determines is not accessible in the current runtime environment.
- **`InaccessibleObjectException`**: a `RuntimeException` that occurs when reflection tries to enable restricted access, such as calling `setAccessible(true)`, but Java does not allow bypassing access checks.

The core distinction is **how the access fails**. `IllegalAccessError` typically involves direct access requested by bytecode during linking or execution. `InaccessibleObjectException` involves reflection trying to unlock a member that is not accessible under current rules.

Java 17 applies strong encapsulation to JDK internal APIs. As a result, legacy libraries relying on reflection into internal packages may encounter `InaccessibleObjectException`; code depending on unexported packages may also encounter linkage errors. This lesson focuses on module and reflection APIs still applicable in Java 17, without relying on obsolete access-relaxation options.

## 1. Where Do These Two Errors Sit in the Exception Hierarchy?

Although both relate to access permissions, they belong to different branches of Java's type hierarchy.

```text
Throwable
├── Exception
│   └── RuntimeException
│       └── InaccessibleObjectException
│
└── Error
    └── LinkageError
        └── IncompatibleClassChangeError
            └── IllegalAccessError
```

| Characteristic | `IllegalAccessError` | `InaccessibleObjectException` |
|---|---|---|
| Hierarchy | `Error` → `LinkageError` | `RuntimeException` |
| Problem category | Linking/access of compiled code | Reflection unable to bypass access checks |
| When typically encountered | When the JVM links or executes direct access | When calling reflection APIs like `setAccessible(true)` |
| Commonly involved mechanisms | Class/member access rules and module boundaries | `AccessibleObject`, `Field`, `Method`, `Constructor` |
| Is it a checked exception? | No | No |
| Primary fix | Fix module dependencies, export packages, or configure runtime properly | Open packages intentionally or stop deep reflection |

### 1.1. IllegalAccessError is a linkage error

`IllegalAccessError` belongs to the `LinkageError` branch. It occurs when the JVM encounters an access requested by compiled code, but the target class or member cannot be accessed in the execution environment.

A typical scenario:

1. Application code is compiled when a library package is exported or granted access via compiler flags.
2. At runtime, the module descriptor or module configuration differs from compile time.
3. The JVM attempts to link a reference to a class/member in a package not exported to the application module.
4. The JVM throws `IllegalAccessError`.

Because this is an `Error`, do not treat it like a normal input error and catch `Exception` to keep running. Fix the module configuration or dependency causing the invalid access.

### 1.2. InaccessibleObjectException is a reflection operation error

`InaccessibleObjectException` belongs to package `java.lang.reflect`. It is thrown when a reflection operation attempts to make an `AccessibleObject` suppress access checks, and doing so is not permitted.

Example:

```java
import java.lang.reflect.Field;

public class StringReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field valueField = String.class.getDeclaredField("value");

        valueField.setAccessible(true); // Java 17: may throw
                                      // InaccessibleObjectException
    }
}
```

In JDK 17, package `java.lang` in module `java.base` is not opened by default for deep reflection from applications. Therefore, enabling access to `String`'s private field is denied.

This does not mean the field does not exist. `getDeclaredField("value")` can locate the field, but the step requesting to bypass access checks is rejected by the module system.

## 2. Essential Foundation: exports and opens

JPMS distinguishes normal API access from *deep reflection* access.

### 2.1. exports: allowing other modules to use public APIs

A module can export a package in `module-info.java`:

```java
module com.example.model {
    exports com.example.model.api;
}
```

A module reading `com.example.model` can access public types in package `com.example.model.api`, provided other Java access conditions are also satisfied.

`exports` primarily supports normal usage of public APIs:

```java
package com.example.model.api;

public class User {
    public String displayName() {
        return "An";
    }
}
```

Another application can declare:

```java
module com.example.app {
    requires com.example.model;
}
```

and use it:

```java
import com.example.model.api.User;

public class Main {
    public static void main(String[] args) {
        User user = new User();
        System.out.println(user.displayName());
    }
}
```

An exported package does not turn private members into public ones. Java's access rules still apply.

### 2.2. opens: allowing deep reflection at runtime

If a framework needs to access private fields, private constructors, or private methods via reflection, the module containing the class needs to open the corresponding package:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.app;
}
```

- `exports` allows `com.example.app` to use the package's public API.
- `opens` allows reflection from `com.example.app` to deeply access members of the package at runtime.

These two directives do not replace each other. `opens` does not automatically make a package an API that can be imported and used directly at compile time. Conversely, `exports` does not by default allow reflection to bypass access checks on private members.

### 2.3. Qualified exports and qualified opens

Permissions can be granted to a specific module:

```java
module com.example.model {
    exports com.example.model.api to com.example.app;
    opens com.example.model.api to com.example.json;
}
```

In this example:

- Only `com.example.app` can use the package's public API.
- Only `com.example.json` is permitted deep reflection into the package.

Scoping permissions to target modules limits the access surface. Do not open packages broadly to every module if only one framework needs it.

### 2.4. open module opens all packages for reflection

A module can declare:

```java
open module com.example.model {
    exports com.example.model.api;
}
```

An `open` module opens all of its packages for deep reflection at runtime. However, that does not mean all packages are automatically exported for other modules to access as APIs at compile time.

Because of its broad scope, `open module` is only appropriate when the design genuinely requires deep reflection across the entire module. If only one package needs it, `opens package to module` expresses intent much more accurately.

## 3. Example: exports Is Not Enough to Access a Private Field via Reflection

Suppose there are two modules:

```text
project/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/api/User.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Module `com.example.model` exports the API package:

```java
module com.example.model {
    exports com.example.model.api;
}
```

Class `User`:

```java
package com.example.model.api;

public class User {
    private final String secret = "internal-value";

    public String name() {
        return "An";
    }
}
```

Application module:

```java
module com.example.app {
    requires com.example.model;
}
```

The application attempts to access the private field:

```java
package com.example.app;

import com.example.model.api.User;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        User user = new User();

        System.out.println(user.name()); // Public API: works

        Field secret = User.class.getDeclaredField("secret");
        secret.setAccessible(true);      // Package not opened: error
        System.out.println(secret.get(user));
    }
}
```

Expected outcome:

- Calling `user.name()` works because the package is exported and the method is public.
- `getDeclaredField("secret")` finds the field.
- `setAccessible(true)` is denied because the package is not opened to the application module; Java throws `InaccessibleObjectException`.

To permit deep reflection from `com.example.app`, the model module can add:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.app;
}
```

After recompiling and running again with this module descriptor, `setAccessible(true)` can enable access to the private field per the package open permission.

**Key point:** `exports` serves public APIs; `opens` serves deep reflection. If a framework needs to read private fields, adding `exports` alone is usually not enough.

## 4. IllegalAccessError in the Module Context

A normal access error caught at compile time is a compiler error. For example, an application module importing an unexported package may report that the package is not visible. `IllegalAccessError` appears when the access was not caught or configuration changed between compile time and runtime.

### 4.1. Module configuration changes after compilation

Suppose a library initially had:

```java
module com.example.library {
    exports com.example.internal;
}
```

An application was compiled and used public classes in package `com.example.internal`.

Later, the library changed its module descriptor:

```java
module com.example.library {
    // com.example.internal is no longer exported.
}
```

If the older application still runs with bytecode referencing classes in that package, the JVM can throw `IllegalAccessError` when linking or executing the access.

This is a classic case where **compile-time and runtime environments no longer share the same module contract**. Simply having `requires com.example.library` does not grant access to every package in the library.

### 4.2. Using --add-exports at compile time and runtime

In some legacy application migration scenarios, export access can be temporarily granted via command-line options:

```bash
javac --module-path mods \
  --add-exports com.example.library/com.example.internal=com.example.app \
  -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

At runtime, the corresponding permission must also be present in the runtime configuration:

```bash
java --module-path mods \
  --add-exports com.example.library/com.example.internal=com.example.app \
  -m com.example.app/com.example.app.Main
```

`--add-exports` grants access to the package's public API to the target module. It does not allow deep reflection into private members; that requires `opens` or `--add-opens`.

If compiled with additional permissions but run without the required runtime permission, the JVM can deny access and throw `IllegalAccessError`.

### 4.3. Do not confuse compiler errors with IllegalAccessError

| Scenario | Typical result |
|---|---|
| Source code imports a package from another module that is not exported | Compiler error: package is not visible |
| Bytecode was compiled in a permitted environment, but runtime no longer exports it | May encounter `IllegalAccessError` |
| Reflection calls `setAccessible(true)` on a private member of an unopened package | `InaccessibleObjectException` |
| Reflection calls `Field.get()` without access rights and without enabling accessible | `IllegalAccessException` |

Do not call every module issue `IllegalAccessError`. Observe whether the error occurs in the compiler, during a reflection call, or when the JVM links bytecode.

## 5. InaccessibleObjectException and Reflection APIs

The Java Reflection API provides several methods to check and adjust accessibility. Understanding their differences is necessary to handle them properly.

### 5.1. setAccessible(true)

`AccessibleObject.setAccessible(true)` asks the JVM to suppress Java language access checks for that reflection object, within the bounds allowed by the module system.

Example:

```java
Field field = User.class.getDeclaredField("secret");
field.setAccessible(true);
String value = (String) field.get(user);
```

If the package of the declaring class is not opened to the calling module, `setAccessible(true)` can throw `InaccessibleObjectException`.

This method is not a way to bypass all module system restrictions. Java 17 still enforces package open rules.

### 5.2. trySetAccessible()

If you want to check whether access can be enabled without receiving `InaccessibleObjectException` when a package is not opened, use `trySetAccessible()`:

```java
Field field = User.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    String value = (String) field.get(user);
    System.out.println(value);
} else {
    System.out.println("Module has not opened package for reflection");
}
```

Result:

- `true`: enabling accessible succeeded; reflection can proceed under granted permissions.
- `false`: Java cannot enable access under current rules; do not proceed to call `get()` as though permission were granted.

`trySetAccessible()` is especially useful for libraries that must support multiple module environments.

### 5.3. canAccess() checks current access permission

`canAccess(Object)` indicates whether the current caller can access the reflection object, considering accessible state and access rules.

```java
Field field = User.class.getDeclaredField("secret");

boolean accessible = field.canAccess(user);
System.out.println(accessible);
```

For instance fields, pass the target object; for static members, pass `null`. This method does not open packages or enable access permissions itself.

You can combine them:

```java
if (!field.canAccess(user) && !field.trySetAccessible()) {
    throw new IllegalStateException("Cannot access field through reflection");
}

String secret = (String) field.get(user);
```

This example assumes the class and object have already been created, and the code lies in a context that can handle checked exceptions declared by reflection.

### 5.4. IllegalAccessException is a different error

Do not confuse `InaccessibleObjectException` with `IllegalAccessException`.

For example, if a private field is not accessible and `setAccessible(true)` has not been called, reading the field can throw the checked exception:

```java
Field field = User.class.getDeclaredField("secret");

// Without calling setAccessible/trySetAccessible.
String secret = (String) field.get(user); // IllegalAccessException
```

Meanwhile:

```java
Field field = User.class.getDeclaredField("secret");
field.setAccessible(true); // InaccessibleObjectException if module is not opened
```

- `IllegalAccessException`: a reflection operation such as `Field.get()`, `Method.invoke()`, or `Constructor.newInstance()` is not permitted to access the member.
- `InaccessibleObjectException`: the request to change the accessible state is denied by the module system.

Both can appear in the same reflection story, but they occur at different steps and are handled differently.

## 6. Strong Encapsulation in Java 17

The Java Platform Module System was introduced in Java 9. A key goal was strongly encapsulating JDK internal packages so applications rely only on supported public APIs.

In transitional releases prior to Java 17, some reflective access to internal APIs had compatibility mechanisms and warnings. Starting in Java 17, JEP 403 completes strong encapsulation of JDK internal elements, except for packages explicitly opened by configuration.

That means:

- Do not depend on internal classes, fields, or methods in packages like `sun.*` or JDK internal implementations.
- Reflection into private members of unopened JDK packages can fail with `InaccessibleObjectException`.
- Legacy libraries may need upgrading if they use deep reflection on JDK internals.
- Exported public APIs can still be used normally according to their contracts.

### 6.1. Example with String's private field

In JDK 17, `String` has an internal field named `value`. This is an implementation detail, not an API applications should depend on.

```java
import java.lang.reflect.Field;

public class StringInternals {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");

        System.out.println(value.getName());

        value.setAccessible(true); // Java 17: InaccessibleObjectException
    }
}
```

The field can be located via reflection, but permission to open it is not granted by default. The internals of `String` can also change across JDK versions; applications should not rely on this field's type or contents.

### 6.2. Do not rely on --illegal-access

The `--illegal-access` option previously supported the module transition in earlier JDK releases. In Java 17, this option no longer provides the previous access-relaxation mechanism.

Do not instruct users to add `--illegal-access=permit` to fix errors on Java 17. Where temporary compatibility is genuinely needed, grant targeted permissions via `--add-opens` or `--add-exports`, and plan to eliminate the internal dependency.

## 7. How Do --add-opens and --add-exports Differ?

These two command-line options are often mentioned when resolving module access errors, but they serve different purposes.

| Option | Permission granted | Used for |
|---|---|---|
| `--add-exports module/package=target` | Exports package to target module | Accessing public APIs of an unexported package |
| `--add-opens module/package=target` | Opens package to target module | Deep reflection into non-public members at runtime |

### 7.1. --add-opens example

To allow a classpath application (unnamed module) to perform deep reflection into package `java.lang` of `java.base`, run:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp out demo.StringReflectionDemo
```

If the application is a named module, specify the target module name:

```bash
java --add-opens java.base/java.lang=com.example.app \
  --module-path mods \
  -m com.example.app/com.example.app.Main
```

`--add-opens` is a runtime permission; it does not make a package an API that can be imported at compile time.

### 7.2. --add-exports example

When access to a public API in an unexported package is needed, targeted export permission can be granted:

```bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
  -cp out demo.LegacyApplication
```

This illustrates the permission-granting mechanism, not a recommendation to depend on `sun.nio.ch`. Internal packages can change or disappear; migrate to supported public APIs.

### 7.3. Grant only necessary permissions

If framework `com.example.json` needs reflection into a model package, prefer opening only that package to that specific module:

```java
module com.example.model {
    opens com.example.model.dto to com.example.json;
}
```

Avoid opening the entire JDK or the entire application to `ALL-UNNAMED` if only one specific module needs access. Broader permissions weaken encapsulation boundaries.

## 8. Identifying Errors from Stack Traces

When encountering an access error, read the exception/error type and the first line belonging to application or library code.

### 8.1. Signs of IllegalAccessError

A stack trace might begin with:

```text
java.lang.IllegalAccessError: class com.example.app.Main
cannot access class com.example.internal.Secret
because module com.example.library does not export
com.example.internal to module com.example.app
```

The exact message depends on the JDK and context, but it generally involves unauthorized direct access to a class/member.

Investigation steps:

1. Identify the class/member mentioned in the message.
2. Find the module owning that package.
3. Inspect the owning module's `module-info.java`.
4. Determine whether the package is exported to the calling module.
5. Compare compile-time module configuration with runtime configuration.
6. Check any `--add-exports` flags passed to both phases if using a compatibility workaround.

### 8.2. Signs of InaccessibleObjectException

A stack trace might look like:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module java.base does not "opens java.lang" to
unnamed module ...
```

Common signs:

- Presence of `java.lang.reflect.InaccessibleObjectException`.
- Stack trace passes through `AccessibleObject.setAccessible(...)` or `trySetAccessible()`.
- Message states that the module does not `opens` the package to the calling module.

Investigation steps:

1. Identify the field/method/constructor the library wants to access.
2. Identify the module containing the declaring class.
3. Identify the module performing reflection.
4. Check whether the package is opened (`opens`) to the calling module.
5. Prefer a public API or a library version that does not require deep reflection.
6. Use targeted `--add-opens` only if the dependency cannot yet be removed.

### 8.3. Signs of IllegalAccessException

If the stack trace reports `java.lang.IllegalAccessException`, inspect the actual reflection call (`Field.get`, `Method.invoke`, `Constructor.newInstance`) and `canAccess()` status. This is a checked exception from the Reflection API, distinct from failure to enable accessible.

## 9. How to Fix Based on Root Cause

No single JVM flag solves every access error. Choose the fix matching the type of access.

### 9.1. When encountering IllegalAccessError

- Ensure the module containing the package exports it to the calling module.
- If the API should not be used directly, replace it with a supported public API.
- Check module descriptors and module path configuration in the runtime environment.
- If using `--add-exports` as a transitional bridge, pass the appropriate permission at runtime and at compile time if needed by the compiler.
- Update or recompile the dependent library if it was built against old module assumptions.

Module descriptor example:

```java
module com.example.library {
    exports com.example.publicapi;
}
```

Applications should only use classes in `com.example.publicapi` if that is the API the library commits to supporting.

### 9.2. When encountering InaccessibleObjectException

- Check whether the framework has a version supporting Java 17 and JPMS.
- If reflecting on application classes, open the necessary package via `opens package to framework.module`.
- If accessing a JDK internal package, find a replacement public API.
- If a transitional workaround is needed, use `--add-opens` with the exact module/package/target.
- Do not call `setAccessible(true)` unconditionally; use `trySetAccessible()` when permissions may vary across environments.

### 9.3. When encountering IllegalAccessException

- Check whether the member is `public` and whether the class/package allows access.
- Check whether the caller is in the right module/package under Java rules.
- If deep reflection is genuinely needed, verify `opens` and use `trySetAccessible()`.
- If deep reflection is unnecessary, use public methods or constructors.

## 10. Designing Modules to Minimize Access Errors

A well-designed module should publish a small, clear API and keep implementations in unexported packages.

Example:

```java
module com.example.billing {
    exports com.example.billing.api;
}
```

Package structure:

```text
com.example.billing
├── api
│   ├── InvoiceService.java
│   └── Invoice.java
└── internal
    ├── InvoiceRepository.java
    └── TaxCalculator.java
```

Other modules only access package `api`. Package `internal` is not exported and therefore is not part of the public API.

If a framework needs reflection on DTOs or entities, open only that package:

```java
module com.example.billing {
    exports com.example.billing.api;
    opens com.example.billing.api to com.example.json;
}
```

Do not open the entire `internal` package simply because a framework needs to read a few DTO fields.

### 10.1. Prefer constructors, accessors, and public APIs

When designing classes yourself, provide clear APIs instead of forcing libraries to access private fields via reflection:

```java
package com.example.billing.api;

public final class Invoice {
    private final String number;

    public Invoice(String number) {
        this.number = number;
    }

    public String number() {
        return number;
    }
}
```

Frameworks or callers can use the public constructor and accessor. If the library supports constructor binding or record binding, this typically depends far less on implementation details.

### 10.2. Open packages only to frameworks that truly need it

Some serialization, dependency injection, ORM, or testing frameworks may need reflection. In those cases, the module descriptor should name the target module explicitly:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.entity to org.example.orm;
}
```

The framework module name must match the dependency's actual module name. If the library runs on the classpath, the caller may be the unnamed module; in that case `ALL-UNNAMED` should only be used as a carefully scoped compatibility configuration.

## 11. Diagnostic Tools for Investigation

### 11.1. Inspecting module descriptors

Use `jar --describe-module` to inspect a JAR's descriptor:

```bash
jar --describe-module --file library.jar
```

The output reports the module name, exported/opened packages, and module requirements. This step is helpful when dependency source code is unavailable.

### 11.2. Analyzing JDK internal dependencies with jdeps

```bash
jdeps --jdk-internals application.jar
```

`jdeps --jdk-internals` helps detect static references to JDK internal APIs in the analyzed artifact. While the tool cannot catch every dynamically constructed reflection call, it can highlight many dependencies to replace before upgrading the JDK.

### 11.3. Finding module and package names

When an error reports a package is not opened or not exported, identify accurately:

- The module containing the target class.
- The package containing the member.
- The module performing the access.
- Whether that package currently has `exports`, `opens`, or neither directive.

You can use `jar --describe-module`, module descriptors in source, and stack traces to piece together this information.

## 12. Common Misconceptions

### 12.1. Both are IllegalAccessException

False. `IllegalAccessError` is an `Error`, `InaccessibleObjectException` is a `RuntimeException`, and `IllegalAccessException` is a checked exception.

### 12.2. Adding exports enables reflection on private fields

False. `exports` permits public API access; deep reflection into private members requires the package to be opened (`opens`).

### 12.3. Adding opens lets code import classes in that package

False. `opens` serves runtime reflection. To use public types directly from another module, the package must be exported.

### 12.4. setAccessible(true) always works if the field exists

False. The module system can reject requests to bypass access checks and throw `InaccessibleObjectException`.

### 12.5. trySetAccessible() throws the same exception

Not when access cannot be enabled under module rules: the method returns `false`. It is designed so callers can check capability before reading/invoking.

### 12.6. IllegalAccessError only happens when using reflection

False. It is a linkage error that can happen with direct bytecode access, such as when a module does not export a package at runtime.

### 12.7. InaccessibleObjectException only happens with JDK classes

False. It can happen with application or third-party library classes if the package is not opened to the module performing deep reflection.

### 12.8. --add-opens and --add-exports are the same

False. One opens deep reflection; the other exports public APIs. Using the wrong option will not fix the underlying issue.

### 12.9. All access errors should be caught and ignored

False. Ignoring them can cause the program to continue with missing data or invalid state. Fix the module contract or API design.

### 12.10. --illegal-access=permit is the fix for Java 17

False. In Java 17, this option no longer provides the access-relaxation mechanism of earlier transitional releases. Use targeted `opens` or `--add-opens` if deep reflection is truly needed.

## 13. Quick Decision Table

| Symptom | Primary diagnosis | Resolution |
|---|---|---|
| `IllegalAccessError` when calling class/member from another module's package | Package not exported or runtime configuration differs from compile time | Check `exports`, module path, and `--add-exports` |
| `InaccessibleObjectException` at `setAccessible(true)` | Package not opened to the reflecting module | Check `opens`, `--add-opens`, or remove deep reflection |
| `trySetAccessible()` returns `false` | Java does not permit enabling deep access | Use a public API or open the package selectively |
| `IllegalAccessException` at `Field.get()`/`Method.invoke()` | Reflection access check failed | Check `canAccess`, `opens`, and the access method |
| Compiler error reporting package is not visible | Package not exported in module descriptor | Fix `exports` or use another public API |

## 14. Practice Exercises

### Exercise 1. Distinguishing error types

A library calls `field.setAccessible(true)` on a private field of a class in a module that does not open the package.

**Question:** Which error may occur?

**Answer:** `InaccessibleObjectException`, because the request to bypass access checks is rejected by the module system.

### Exercise 2. Direct access to an unexported package

An application was compiled when a library package was exported, but runtime uses a module descriptor that no longer exports that package.

**Question:** Which error may occur when the JVM links the access?

**Answer:** `IllegalAccessError`, because bytecode requests access to a class/member that is not permitted in the current runtime environment.

### Exercise 3. Choosing a directive

A framework `com.example.json` needs to read private fields in package `com.example.model.dto`. Which directive should be used?

**Answer:** `opens com.example.model.dto to com.example.json;`. If the application also needs to import and call public APIs in that package, add `exports` separately.

### Exercise 4. Safer reflection checks

Complete the code snippet to read the field only if accessible can be enabled:

```java
Field field = User.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    System.out.println(field.get(user));
} else {
    System.out.println("Access is not available");
}
```

**Answer:** The snippet is complete. `trySetAccessible()` returns `true` when permission is enabled and `false` when it cannot be. `get()` can still throw `IllegalAccessException` and must be handled according to the enclosing method's signature.

### Exercise 5. exports or opens?

A module needs to let another module call the public method `User.name()`, without accessing private fields.

**Answer:** `exports` on the package containing `User` is sufficient if other Java access rules are met. There is no need to open the package for deep reflection.

### Exercise 6. Distinguishing IllegalAccessException

`Field.get(user)` throws `IllegalAccessException` when a private field has not been made accessible.

**Question:** Is this `InaccessibleObjectException`?

**Answer:** No. `IllegalAccessException` occurs when the field-reading operation is not allowed; `InaccessibleObjectException` occurs when the request to suppress access checks is denied.

### Exercise 7. Choosing a JVM option

A legacy library on the classpath needs deep reflection into package `java.base/java.lang` while migrating the application.

**Answer:** `--add-opens java.base/java.lang=ALL-UNNAMED` can be used as a temporary compatibility measure. Upgrade or replace the library to remove reliance on JDK internals.

### Exercise 8. Why not use --illegal-access=permit?

**Answer:** In Java 17, this option no longer provides the access-relaxation mechanism of earlier transitional versions. Use targeted `opens` or `--add-opens` if deep reflection is genuinely needed.

## 15. Official References

- [JDK 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception thrown when access checks cannot be suppressed by reflection.
- [JDK 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`, `trySetAccessible`, `canAccess`, and module rules.
- [JDK 17 API — IllegalAccessError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html): linkage error when accessing a disallowed class/member.
- [JDK 17 API — IllegalAccessException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html): checked exception from an unauthorized reflection operation.
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declarations, `requires`, `exports`, and `opens`.
- [JDK 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): runtime API for inspecting and manipulating module information.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation enforced in Java 17 and the status of `--illegal-access`.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): design of the Java module system.

**Key takeaway:** `IllegalAccessError` is a linkage error when bytecode accesses a class/member not permitted at runtime. `InaccessibleObjectException` is a runtime exception when reflection asks to bypass access checks on an unopened package. `exports` grants public API access; `opens` grants deep reflection access. When investigating, identify the package-owning module, the calling module, the type of access operation, and the runtime configuration before choosing a fix.
