# Verifying Module Boundaries and Reflection in Java 17

The Java Platform Module System (JPMS) establishes explicit boundaries between modules: which module can read which module, which packages are exposed for normal access, and which packages are opened so frameworks can use deep reflection. When running on Java 17, the fact that a class or private member can be discovered via reflection does not mean the program is permitted to read, modify, or invoke that member.

This lab builds two named modules to directly verify these boundaries:

- Module `com.example.model` exposes a public API and encapsulates a private field.
- Module `com.example.inspector` calls the public API and then attempts to access the private field via reflection.
- Initially the package is only `exports`-ed, so the public API works while deep reflection is blocked.
- Next, the package is opened to the specific module via qualified `opens`, and verified again.
- Finally, `--add-opens` is passed at launch to observe the same runtime behavior without modifying the module descriptor.

The goal is to know how to verify access permissions in a Java 17 runtime, interpret the resulting errors accurately, and choose the narrowest necessary package-opening scope.

## 1. Three Conditions for Module Access

For one module to use a type in another module, distinguish three concepts:

| Concept | Question | Common declaration |
| --- | --- | --- |
| Readability | Can the calling module read the module containing the type? | `requires` |
| Export | Does the package expose public types/members to the calling module? | `exports` |
| Open | Does the package permit deep reflection into non-public members? | `opens` |

These three permissions serve different purposes:

- `requires` establishes a module readability relationship. It does not automatically expose packages.
- `exports` permits normal access to public types and public members in the exported package. It does not open private fields or private methods.
- `opens` permits deep reflection at runtime into the package. It does not allow source code to import public types from that package as an exported compile-time API.

Example:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.persistence to com.example.orm;
}
~~~

In this configuration, other modules can call the public API of `com.example.model.api` if they read the model module. Separately, only `com.example.orm` is permitted to perform deep reflection into the `persistence` package. Other modules do not receive that open permission.

### exports Does Not Imply opens

This is the key distinction to verify experimentally:

| Declaration | Import public type at compile time | Call public API | Deep reflection on private members |
| --- | --- | --- | --- |
| Neither exported nor opened | No | No | No |
| `exports p` | Yes | Yes | No |
| `opens p` | No | Not via normal access | Yes at runtime |
| `exports p; opens p;` | Yes | Yes | Yes |
| `exports p to m; opens p to m;` | Only the specified module | Yes for the specified module | Yes for the specified module |

A package can be both exported and opened, but do so only when both independent needs exist: a public API for callers and deep reflection for a framework.

## 2. Setting Up a Two-Module Project

Create the directory structure:

~~~text
module-reflection-lab/
  src/
    com.example.model/
      module-info.java
      com/example/model/api/Account.java
    com.example.inspector/
      module-info.java
      com/example/inspector/Main.java
~~~

Place both modules on the module source path. Each module directory has its own `module-info.java`.

### Module com.example.model

File `src/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

The module exports only the API package. There is no `opens` directive yet.

File `src/com.example.model/com/example/model/api/Account.java`:

~~~java
package com.example.model.api;

public final class Account {
    private int balance = 1250;

    public int balance() {
        return balance;
    }
}
~~~

`Account` has a public `balance()` method and a private `balance` field. The public method is the contract other modules may use; the field is internal state.

### Module com.example.inspector

File `src/com.example.inspector/module-info.java`:

~~~java
module com.example.inspector {
    requires com.example.model;
}
~~~

The `requires` clause lets `inspector` read the `model` module. Because `model` exports `com.example.model.api`, `inspector` can import `Account`.

File `src/com.example.inspector/com/example/inspector/Main.java`:

~~~java
package com.example.inspector;

import com.example.model.api.Account;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account();

        // Access the public API per the module contract.
        System.out.println("Public balance = " + account.balance());

        Field field = Account.class.getDeclaredField("balance");
        System.out.println("canAccess before = "
                + field.canAccess(account));

        boolean opened = field.trySetAccessible();
        System.out.println("trySetAccessible = " + opened);

        if (opened) {
            System.out.println("canAccess after = "
                    + field.canAccess(account));
            System.out.println("Private balance = "
                    + field.get(account));
        } else {
            System.out.println(
                    "Deep reflection is not permitted for this package");
        }
    }
}
~~~

The example uses `getDeclaredField()` to obtain metadata about a field declared directly in the class. Discovering the `Field` does not grant permission to read its value. `trySetAccessible()` tests whether deep access can be enabled in the current module context.

## 3. Compiling and Running with Only an Exported Package

From the `module-reflection-lab` directory, compile both modules:

~~~bash
javac --release 17 \
      --module-source-path src \
      -d out \
      -m com.example.model,com.example.inspector
~~~

Run the `inspector` module:

~~~bash
java --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

Expected output:

~~~text
Public balance = 1250
canAccess before = false
trySetAccessible = false
Deep reflection is not permitted for this package
~~~

The public API works because:

1. `com.example.inspector` reads `com.example.model` via `requires`.
2. `com.example.model` exports `com.example.model.api`.
3. `Account` and `balance()` are `public`.

Deep reflection is denied because the package is only exported, not opened to `inspector`. This demonstrates that `exports` does not expose private members.

### Why Does getDeclaredField() Still Succeed?

`getDeclaredField("balance")` returns metadata for a field declared in the class. It does not mean the caller has permission to access the field's value. Access rights are enforced when reading/writing via `Field.get()`, `Field.set()`, or when requesting to suppress access checks.

Do not write logic assuming that:

~~~java
Field field = Account.class.getDeclaredField("balance");
Object value = field.get(account);
~~~

will always succeed merely because `getDeclaredField()` did not throw. Without permission, `get()` will throw `IllegalAccessException`.

## 4. Distinguishing canAccess, trySetAccessible, and setAccessible

These APIs have distinct responsibilities:

| API | Meaning | When not permitted |
| --- | --- | --- |
| `canAccess(object)` | Checks whether the member is accessible under current access state | Returns `false` |
| `trySetAccessible()` | Attempts to enable suppressing language access checks if module boundaries allow | Returns `false` |
| `setAccessible(true)` | Requests enabling deep access | May throw `InaccessibleObjectException` |
| `setAccessible(false)` | Disables the accessible override | Restores standard access checks |

For instance fields, pass the target object to `canAccess`. For static fields, pass `null`. Passing the wrong kind of argument throws `IllegalArgumentException`.

### Testing setAccessible(true) When the Package Is Not Open

You can replace the access attempt in `Main` with:

~~~java
try {
    field.setAccessible(true);
    System.out.println("setAccessible succeeded");
    System.out.println("Private balance = " + field.get(account));
} catch (java.lang.reflect.InaccessibleObjectException ex) {
    System.out.println("Deep reflection denied: "
            + ex.getMessage());
}
~~~

When `model` only exports the package, `setAccessible(true)` on a private field throws `InaccessibleObjectException`. This runtime exception indicates that the module system forbids opening deep access as requested.

`trySetAccessible()` fits cases where code wants to probe whether access can be opened without using exceptions for normal control flow. If it returns `false`, a framework should report a clear configuration error or fall back to a public API.

### Do Not Confuse Metadata with Access Rights

Reflection can list non-public methods or fields in certain contexts, yet invoking, reading, or modifying them still requires passing access checks. All of the following can fail if the package/module forbids it:

- `Field.get()` and `Field.set()`.
- `Method.invoke()`.
- `Constructor.newInstance()`.
- `MethodHandles.privateLookupIn()`.

## 5. Opening the Right Package to the Right Module

If a framework genuinely requires deep reflection on `Account`, update the module descriptor of the module owning the package.

File `src/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.inspector;
}
~~~

This is a **qualified opens**. Package `com.example.model.api` is opened only to `com.example.inspector`.

Recompile:

~~~bash
javac --release 17 \
      --module-source-path src \
      -d out \
      -m com.example.model,com.example.inspector
~~~

Run again:

~~~bash
java --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

Expected output:

~~~text
Public balance = 1250
canAccess before = false
trySetAccessible = true
canAccess after = true
Private balance = 1250
~~~

`canAccess` is initially `false` because the private field does not yet have its accessible override enabled. Once `trySetAccessible()` succeeds, standard access checks are bypassed on that `Field` instance and `canAccess` returns `true`.

### Why Use Qualified opens?

The declaration:

~~~java
opens com.example.model.api to com.example.inspector;
~~~

limits deep reflection privileges to the specific module that needs them. Opening the package to all modules:

~~~java
opens com.example.model.api;
~~~

allows every eligible module to deep-reflect into that package. Broader exposure weakens encapsulation and makes internal implementation changes harder to control.

If an ORM framework is module `com.example.orm`, open the package to that ORM module. Do not open it to an inspector module just because this lab uses that name; the target module in production must be the module actually performing reflection.

## 6. Verifying with --add-opens at Launch

You can test opening a package without modifying `module-info.java`. Revert the module descriptor to `exports`-only, recompile, and run:

~~~bash
java --module-path out \
     --add-opens com.example.model/com.example.model.api=com.example.inspector \
     -m com.example.inspector/com.example.inspector.Main
~~~

The deep reflection result matches declaring a qualified `opens` in the descriptor. The `--add-opens` flag opens the package at runtime for the specified target module.

This is useful when:

- Diagnosing a legacy framework that relies on deep reflection.
- Confirming whether a package/module boundary is the root cause of an error.
- Providing a narrowly scoped workaround during a migration period.

If a workaround becomes a long-term deployment flag, document the source module, package, target module, rationale, and removal plan. For application modules you own, declaring qualified `opens` in `module-info.java` is usually easier to review and maintain than accumulating JVM flags.

### Callers on the Classpath

Code running on the classpath belongs to the unnamed module. If a classpath application needs deep reflection into a named module's package, the target can be `ALL-UNNAMED`:

~~~bash
java --module-path mods \
     --add-modules com.example.model \
     --add-opens com.example.model/com.example.model.api=ALL-UNNAMED \
     -cp app.jar \
     com.example.Main
~~~

`ALL-UNNAMED` opens the package to all unnamed modules. This is broader than a qualified open to a single named module; use it only when the caller genuinely runs on the classpath and requires that access.

`--add-opens` is a runtime option. It does not make a package exported so that other source code can import its public types at compile time.

## 7. Inspecting Boundaries with the Module API

Java provides runtime APIs to query whether a module reads another module, exports a package, or opens a package to a specific module.

Add the following to `Main`:

~~~java
Module sourceModule = Account.class.getModule();
Module callerModule = Main.class.getModule();
String packageName = "com.example.model.api";

System.out.println("Source module = " + sourceModule.getName());
System.out.println("Caller module = " + callerModule.getName());
System.out.println("Caller can read source = "
        + callerModule.canRead(sourceModule));
System.out.println("Package exported to caller = "
        + sourceModule.isExported(packageName, callerModule));
System.out.println("Package open to caller = "
        + sourceModule.isOpen(packageName, callerModule));
~~~

When `model` only exports the package, expected output:

~~~text
Caller can read source = true
Package exported to caller = true
Package open to caller = false
~~~

After adding qualified `opens` for `com.example.inspector`:

~~~text
Caller can read source = true
Package exported to caller = true
Package open to caller = true
~~~

Related methods:

| API | Purpose |
| --- | --- |
| `Module.getName()` | Returns the module name; unnamed modules return `null` |
| `Module.canRead(other)` | Checks the readability relationship |
| `Module.isExported(packageName, other)` | Checks whether the package is exported to the target module |
| `Module.isOpen(packageName, other)` | Checks whether the package is open for deep reflection to the target module |
| `Class.getModule()` | Returns the module containing the class |

This provides a direct check in application or diagnostic code. Interpret `isExported()` and `isOpen()` with respect to the specific target module; a package may be open to module A while closed to module B.

## 8. Verifying MethodHandles.privateLookupIn

Field reflection is not the only dynamic access mechanism. `MethodHandles` provides privileged lookups and `VarHandle` access to fields.

Add this snippet inside `inspector`:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Account.class,
                MethodHandles.lookup());

VarHandle balanceHandle = privateLookup.findVarHandle(
        Account.class,
        "balance",
        int.class);

int value = (int) balanceHandle.get(account);
System.out.println("Balance through VarHandle = " + value);
~~~

For this code to run, `com.example.model.api` must be opened to `inspector`. If the package is not open, `privateLookupIn()` throws `IllegalAccessException`.

`privateLookupIn()` is not a backdoor around JPMS. The caller must have readability to the target module, and the target package must be open to the caller module under module access rules.

If you only need to invoke public methods, use `publicLookup()` or call the public API directly. Never request a private lookup when a public API already meets the requirement.

## 9. Testing an Unexported Package

Try narrowing the `model` module:

~~~java
module com.example.model {
    // Do not export com.example.model.api
}
~~~

Now `inspector` fails to compile code containing:

~~~java
import com.example.model.api.Account;
~~~

because the package is not exported to `inspector`. This is a compile-time API access error.

If a package is `opens` without `exports`, runtime deep reflection permission does not turn the package into a public compile-time API. A framework can use appropriate runtime mechanisms to operate on types supplied to it, while other modules still cannot import those types as public APIs.

### When to Use --add-exports?

If you need to grant normal access to public types in an unexported package, `--add-exports` adds compile-time or runtime export permission for the target module:

~~~bash
javac --release 17 \
      --module-path mods \
      --add-exports com.example.model/com.example.model.internal=com.example.inspector \
      ...
~~~

At runtime, the matching flag is also required:

~~~bash
java --module-path mods \
     --add-exports com.example.model/com.example.model.internal=com.example.inspector \
     -m com.example.inspector/com.example.inspector.Main
~~~

`--add-exports` grants normal access to public types and members in the additionally exported package. It does not allow accessing private members. For deep reflection, you need `opens` or `--add-opens`.

Do not use `--add-exports` to treat internal JDK packages as stable APIs. If an application depends on `jdk.internal.*` packages, migrate to supported public APIs or libraries instead.

## 10. open module and Broader Exposure

You can declare:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

`open module` opens all packages of the module for deep reflection at runtime. It does not automatically export all packages for normal Java access.

This is a much broader scope than:

~~~java
opens com.example.model.api to com.example.inspector;
~~~

In real applications, prefer qualified `opens` for specific packages and modules. Use `open module` only when broad framework requirements demand it, after understanding the impact and accepting that no package in the module remains closed against deep reflection.

## 11. Reading and Classifying Reflection Errors

Common errors encountered when verifying module boundaries:

| Exception/error | Common meaning | Resolution |
| --- | --- | --- |
| `InaccessibleObjectException` | Cannot enable accessible override because module/package is not open | Identify source module, package, and caller; use public API or open the package narrowly |
| `IllegalAccessException` | Reflection or `MethodHandles` operation lacks access rights | Check `exports`/`opens`, readability, and access modifiers |
| `NoSuchFieldException` | Requested field does not exist on the queried class | Verify name/type; avoid relying on private implementation fields |
| `NoSuchMethodException` | Requested method/signature does not exist | Check API version and method signature |
| `ClassNotFoundException` | Class not found on class loader/module path | Check module resolution, classpath, and class name |
| `NoClassDefFoundError` | Required runtime class could not be loaded or initialization failed | Check dependencies/runtime and root cause in logs |
| `InvocationTargetException` | Invoked method threw an exception internally | Inspect `getCause()` for the underlying target exception |
| `IllegalArgumentException` from `canAccess` | Invalid receiver passed, e.g., instance vs. static mismatch | Pass an instance for instance members and `null` for static members |

### Diagnostic Details to Record When Reporting Errors

When a framework fails to access a member, record:

- Class name and package containing the member.
- Module of the target class.
- Module of the caller.
- Member name and kind (field/method/constructor).
- Access modifier.
- `canRead`, `isExported`, and `isOpen` relative to the caller.
- JDK vendor/version.
- Full stack trace and JVM arguments.

These details help separate module boundary errors from missing classes, dependency version mismatches, or logic errors inside invoked methods.

## 12. Tools for Inspecting Modules Outside Runtime

Beyond the `Module` API, JDK 17 tools let you inspect module graphs and artifacts.

### Displaying Module Resolution

~~~bash
java --show-module-resolution \
     --module-path out \
     -m com.example.inspector/com.example.inspector.Main
~~~

This option prints which modules are resolved at startup. It helps catch missing modules or unexpected dependency graphs.

### Inspecting a JAR's Module Descriptor

~~~bash
jar --describe-module --file path/to/library.jar
~~~

This command shows whether a JAR has an explicit module descriptor or is treated as an automatic module, along with its packages and declared relationships from artifact metadata.

### Checking the Dependency Graph

~~~bash
jdeps --module-path out --check com.example.inspector
~~~

`jdeps` analyzes module dependencies and flags certain module-graph issues. Use its output together with module descriptors and runtime tests; static analysis does not prove every runtime reflective access will succeed.

### Finding Dependencies on JDK Internals

~~~bash
jdeps --jdk-internals application.jar
~~~

This option helps locate static references to internal JDK APIs. String-based reflection or dynamic class loading may not be fully detected, so combine it with source search and runtime testing.

## 13. Verifying from the Classpath and Unnamed Modules

Many applications still run code on the classpath. That code resides in the unnamed module. When interacting with a named module:

- The caller must read the module containing the type.
- The package must still be exported if code accesses public types/members normally.
- Deep reflection still requires the package to be open to the caller.
- `ALL-UNNAMED` is the target name when opening a package to unnamed modules.

Example:

~~~bash
java --module-path mods \
     --add-opens com.example.model/com.example.model.api=ALL-UNNAMED \
     -cp app.jar \
     com.example.Main
~~~

If you only need to open to a single named module, specify that module name instead of `ALL-UNNAMED`. This minimizes exposure and keeps configuration easier to govern.

JARs placed on the module path without `module-info.class` become automatic modules. Automatic modules have broader export and readability rules than tightly encapsulated named modules. When testing module boundaries, use named modules with explicit descriptors so automatic module behavior does not mask issues.

## 14. Verifying Compatibility of Reflection-Based Frameworks

ORM frameworks, serializers, dependency injectors, mappers, mocking libraries, and test engines rely heavily on reflection. When migrating an application to Java 17, audit which packages each framework accesses and why.

Workflow:

1. Run tests on the target JDK 17 vendor and version.
2. Look for `InaccessibleObjectException` and `IllegalAccessException`.
3. Identify whether the target package belongs to your application, a third-party library, or the JDK.
4. Upgrade frameworks to versions supporting Java 17.
5. Prefer constructors, public accessors, annotations, or SPIs published by the framework.
6. If an application package requires deep reflection, add qualified `opens` on that exact package for the framework module.
7. If `--add-opens` is needed temporarily, document scope, reason, and removal plan.
8. Rerun tests on the production-equivalent module path/classpath and runtime.

If an error occurs when a framework accesses private JDK members, do not reflexively open all of `java.base`. Upgrade to a framework version that supports strong encapsulation or adopt a different integration mechanism.

### Distinguishing Application Packages from JDK Packages

For application packages, the development team controls `module-info.java` and can intentionally open a package to a framework.

For JDK packages, the application does not own the system module descriptors. `--add-opens` can provide a narrowly scoped runtime workaround, but it does not turn private implementations into stable APIs. Prefer published Java SE APIs.

## 15. Writing Automated Tests for Module Boundaries

These checks can be placed in the test suite of a modular application. For example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.model.api.Account;
import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

class ModuleBoundaryTest {
    @Test
    void apiIsExportedButPrivateStateIsNotOpen() throws Exception {
        Account account = new Account();
        Module source = Account.class.getModule();
        Module caller = getClass().getModule();

        assertTrue(caller.canRead(source));
        assertTrue(source.isExported(
                "com.example.model.api", caller));
        assertFalse(source.isOpen(
                "com.example.model.api", caller));

        Field balance = Account.class.getDeclaredField("balance");
        assertFalse(balance.canAccess(account));
        assertFalse(balance.trySetAccessible());
    }
}
~~~

This test verifies that the module configuration has not opened the package to the caller. If the module descriptor adds a qualified `opens`, update the test expectations accordingly. Do not assert a package is always closed if the design intentionally opens it to an ORM.

Another test can verify that a package is intentionally opened:

~~~java
@Test
void persistencePackageIsOpenToOrm() {
    Module source = Account.class.getModule();
    Module orm = OrmEntryPoint.class.getModule();

    assertTrue(source.isOpen(
            "com.example.model.persistence", orm));
}
~~~

In this example, `OrmEntryPoint` is a class belonging to the actual ORM module. Place the test in a module with appropriate visibility and verify the exact package the framework needs.

### Do Not Treat Private Fields as Business Contracts

Module boundary tests exist to verify encapsulation configuration. They should not turn every private field of a domain object into a test contract. When verifying business logic, test public behavior. Only test deep reflection when validating framework integration or module configuration itself.

## 16. Practice Checklist

When verifying module boundaries and reflection:

1. Identify the source module, caller module, and class package.
2. Confirm the caller has readability to the source module.
3. Confirm the package is exported if source code needs to call its public API.
4. Check `Module.isExported()` and `Module.isOpen()` for the exact caller.
5. Use `getDeclaredField()`/`getDeclaredMethod()` to retrieve metadata without mistaking member discovery for access permission.
6. Use `canAccess()` to check current access state.
7. Use `trySetAccessible()` to probe deep reflection without relying on exceptions for control flow.
8. Use qualified `opens` for the exact package and framework module when genuinely needed.
9. Use `--add-opens` as an explicitly scoped runtime configuration for diagnostics or migration.
10. Use `MethodHandles.privateLookupIn()` only when the package is open and privileged lookup is required.
11. Distinguish `--add-exports` for public access from `--add-opens` for deep reflection.
12. Run tests on JDK 17 with a production-like module path.
13. Never open JDK internals by default; upgrade frameworks or use public APIs.

## 17. Practice Conclusion

A module can publish a public API while keeping its private implementation encapsulated. `requires` declares which module reads which, `exports` publishes the public API, and `opens` permits runtime deep reflection. The `Module`, `AccessibleObject`, and `MethodHandles` APIs let you verify these permissions directly in Java 17.

When a framework needs deep access, open only the required package to the specific module and back it up with tests. When using `--add-opens`, treat it as governed runtime configuration with an owner and documented rationale. This preserves module boundaries, catches reflection failures early, and avoids unnecessary coupling to internal JDK implementations.

## Java 17 References

- [Java Language Specification, Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html)
- [Module API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [AccessibleObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [MethodHandles API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [javac options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
