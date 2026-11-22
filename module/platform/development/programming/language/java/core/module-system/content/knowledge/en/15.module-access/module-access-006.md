# IllegalAccessError, IllegalAccessException, and InaccessibleObjectException

These three error types all relate to access permissions for a class, method, field, or constructor in Java, yet they occur at different times and have different resolutions. When working with the Java Platform Module System (JPMS), you must distinguish normal Java access, cross-module access, and deep reflective access.

- `IllegalAccessError` is an **Error** that occurs when the JVM executes or links bytecode and detects that the code lacks access permission.
- `IllegalAccessException` is a **checked exception**, commonly seen when reflection attempts to invoke or read a member that the caller is not permitted to access.
- `InaccessibleObjectException` is an **unchecked exception** thrown when reflection tries to enable restricted access, typically because a module's package is not open to the calling module.

## 1. Quick Comparison

| Characteristic | IllegalAccessError | IllegalAccessException | InaccessibleObjectException |
|---|---|---|---|
| Kind | Error | Checked exception | Unchecked exception |
| Hierarchy | `IncompatibleClassChangeError → LinkageError → Error` | `ReflectiveOperationException → Exception` | `RuntimeException` |
| Common timing | JVM links or executes bytecode | Reflection performs an operation and the access check fails | Reflection calls `setAccessible(true)` but the module disallows it |
| Common context | Accessing an unexported class/member or access permissions changed after compilation | `Field.get`, `Method.invoke`, `Constructor.newInstance` | `AccessibleObject.setAccessible` |
| Primary resolution | Fix module descriptor, module graph, or binary access permissions | Check access rights; use a public API or open the package if deep reflection is needed | Use a public API, declare `opens`, or configure `--add-opens` appropriately |

Do not catch all three in a single generic catch block and ignore them. They represent three distinct situations: a bytecode linkage error, a rejected reflection operation, and a deep reflection request disallowed by the module.

## 2. IllegalAccessError

`IllegalAccessError` belongs to the `LinkageError` family. The JVM throws this error when compiled code references a class or member, yet at runtime the actual access permissions do not allow that operation.

Common causes:

- A class or member used to be public, but the library was replaced with a version that reduced its access visibility.
- Code was compiled when a package was exported, yet the module descriptor at runtime no longer exports that package to the calling module.
- The application was compiled with `--add-exports`, yet the corresponding export configuration is missing at runtime.
- One module can read another module, yet the needed package is not exported to the calling module.

### Example with JPMS

Suppose a library declares the module:

```java
module com.acme.library {
    // Package com.acme.library.internal is not exported.
}
```

Another application may declare:

```java
module com.acme.application {
    requires com.acme.library;
}
```

The `requires` clause establishes a readability relationship: the application module can read the library module. However, that does not automatically make all of the library's packages accessible. If the application's bytecode references a class in `com.acme.library.internal` and that package is not exported to the application, the JVM can throw `IllegalAccessError` when linking or executing that reference.

To allow direct access to public types in the package, the library module can export the package:

```java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.internal to com.acme.application;
}
```

The second line is a **qualified export**: only the module `com.acme.application` is allowed direct access to public types in the internal package. If the package is meant for only one specific module, this limits the exposed API scope.

When quick verification or compatibility with an unmodifiable library is needed, you can use a launcher option:

```bash
java --add-exports=com.acme.library/com.acme.library.internal=com.acme.application \
     -m com.acme.application/com.acme.application.Main
```

If code referencing an unexported package needs to be compiled, the corresponding `--add-exports` configuration must also be passed to the compiler. Compile-time and runtime configurations must stay consistent.

`IllegalAccessError` usually points to a mismatch between compile-time assumptions and the runtime module descriptor, library version, or module path configuration. Check the accessed class and member, their owning module, whether the package is exported to the caller, and the actual JVM options.

## 3. IllegalAccessException

`IllegalAccessException` is a checked exception in the `ReflectiveOperationException` family. It typically occurs when a reflection operation tries to read a field, invoke a method, or instantiate an object via a constructor that the caller lacks permission to access.

For example, a class has a private field:

```java
package com.acme.model;

public class Account {
    private String secret = "internal-value";
}
```

Another class attempts to read the field via reflection:

```java
import java.lang.reflect.Field;
import com.acme.model.Account;

public class ReflectionExample {
    public static void main(String[] args) throws Exception {
        Account account = new Account();

        Field field = Account.class.getDeclaredField("secret");
        Object value = field.get(account); // IllegalAccessException
    }
}
```

`getDeclaredField` locates the field, even when the field is private. However, locating a member does not mean the caller is allowed to read it. When `field.get(account)` performs its access check, Java can throw `IllegalAccessException`.

Reflection operations that commonly throw this exception include:

- `Field.get` and `Field.set` when the caller is not permitted to read or write the field.
- `Method.invoke` when the caller is not permitted to call the method.
- `Constructor.newInstance` when the caller is not permitted to invoke the constructor.
- Certain lookup or invocation operations via `MethodHandles.Lookup` when the lookup lacks sufficient permissions.

### How to Handle It

Prefer public APIs provided by the class or library. If reflection is genuinely necessary, check the access permissions of both the member and its declaring class.

When the package has already been opened by the module to the calling module, you can enable deep access before reading the field:

```java
Field field = Account.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(account);
    System.out.println(value);
} else {
    System.out.println("Cannot enable field access");
}
```

`trySetAccessible()` returns `true` if access could be enabled and `false` otherwise. This method was added in Java 9. If enabling access is skipped or fails, subsequent reflection operations can still throw `IllegalAccessException`.

An important note about `Method.invoke`: if the target method itself throws an exception, reflection normally wraps that exception in `InvocationTargetException`. This differs from `IllegalAccessException`, which indicates the caller was not permitted to invoke the method.

## 4. InaccessibleObjectException

`InaccessibleObjectException` is an unchecked exception in `java.lang.reflect`, added in Java 9 alongside the module system. It occurs when code asks reflection to bypass access checks, yet JPMS disallows opening that access.

For example, an application wants to read a private field of `Account`:

```java
Field field = Account.class.getDeclaredField("secret");
field.setAccessible(true); // May throw InaccessibleObjectException
```

If `com.acme.model` is a package in a named module and that module does not open the package to the application's module, calling `setAccessible(true)` can fail with `InaccessibleObjectException`.

The difference from `IllegalAccessException` is when the error occurs:

- `IllegalAccessException` occurs when the actual reflection operation is rejected by an access check.
- `InaccessibleObjectException` occurs immediately when the request to enable access-check bypass is rejected.

### Why exports Is Not Enough

In JPMS, `exports` and `opens` serve two different purposes:

- `exports` allows other modules to access public types in the package under normal Java access rules.
- `opens` allows reflection to perform deep access into members, including private ones, of the package at runtime.

Therefore, exporting a package does not permit a framework to access private fields via `setAccessible(true)`. When deep reflection is required, the module containing the class must open the package to the calling module.

### Opening a Package in module-info.java

You can open a package to all other modules:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal;
}
```

Or open the package only to a specific framework:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.framework;
}
```

This is **qualified opens**. Only the module named in the declaration is granted deep reflection access to that package.

If all packages of a module need to be open for reflection, the module can be declared as an open module:

```java
open module com.acme.model {
    requires java.sql;
}
```

An open module opens all of its packages for runtime reflection. You should not and cannot combine the `open` keyword with separate `opens` directives in the same module descriptor. Choose only the level of exposure you actually need.

### Using --add-opens at Runtime

When you cannot modify a library's module descriptor, you can open a package via a JVM option:

```bash
java --add-opens=com.acme.model/com.acme.model.internal=com.acme.framework \
     -m com.acme.application/com.acme.application.Main
```

If the reflection code runs on the classpath, the caller belongs to the unnamed module. In that case, you can use:

```bash
java --add-opens=com.acme.model/com.acme.model.internal=ALL-UNNAMED \
     -jar application.jar
```

`--add-opens` configures package opening for reflection at runtime. It does not replace `--add-exports` to allow normal code to directly reference public types in an unexported package.

## 5. Placing All Three Errors in the Same Scenario

Suppose module `com.acme.model` contains class `com.acme.model.internal.Account` with a private field `secret`. Module `com.acme.application` needs to work with that class.

| Operation | Possible Outcome | Reason |
|---|---|---|
| Bytecode directly accesses a class in an unexported package | `IllegalAccessError` | JVM denies cross-module access |
| Reflection calls `field.get(account)` without enabling access and the access check fails | `IllegalAccessException` | Reflection lacks permission to read the field |
| Reflection calls `field.setAccessible(true)` while the package is not open | `InaccessibleObjectException` | JPMS disallows bypassing access checks |

A module may simultaneously need both direct access and deep reflection. In that case, identify each goal accurately:

- Accessing a public API from another module: use `requires` and `exports`.
- Reflecting on private members: use `opens`.
- Accessing an internal package via bytecode: reconsider module boundaries; if truly needed, use a qualified export.
- Reflecting on another module's internal package: open the package selectively to the framework module that needs it.

## 6. Troubleshooting Workflow

### Step 1: Identify the Error and Failing Line

Read the full exception/error name and stack trace. Determine whether the failure occurred during bytecode linkage, a reflection invocation, or enabling reflective access.

Do not guess solely from the name of the accessed class. The same class can cause different errors depending on the operation and module configuration.

### Step 2: Identify the Caller Module and Target Class's Module

Check:

- Whether the running class belongs to a named module or the unnamed module.
- Which module the target class belongs to.
- Whether the target package is exported to the caller.
- Whether the target package is open to the caller.
- Whether the caller module reads the target module via `requires`.

You can run the following command to inspect module metadata in a JAR:

```bash
jar --describe-module --file libs/model.jar
```

For a running module, the `--show-module-resolution` option helps observe module resolution:

```bash
java --show-module-resolution -m com.acme.application/com.acme.application.Main
```

### Step 3: Pick the Right Mechanism

- If you see `IllegalAccessError`, check bytecode access permissions, `exports` declarations, the module path, and `--add-exports` configuration.
- If you see `IllegalAccessException`, check normal reflection access permissions and whether enabling deep access is genuinely needed.
- If you see `InaccessibleObjectException`, check whether the package is open to the exact caller module; consider `opens` or `--add-opens`.

### Step 4: Prefer Fixing at the API Boundary

If an application frequently needs to access private fields of another module, that can be a sign that the API does not yet provide the necessary operation. Consider adding an appropriate public method or interface instead of opening an entire internal package.

If a framework needs reflection for dependency injection, serialization, or mapping, open the specific package to the specific framework module. Avoid using `ALL-UNNAMED` or opening the whole module when only one package and one caller need access.

### Step 5: Verify Both Compile Time and Runtime

Options used during compilation are not automatically preserved when running the application. Check the build command, plugin configuration, module path, and actual launcher command. After fixing, re-run using the real deployment method to confirm the error is gone.

## 7. Common Pitfalls

- **Assuming `requires` grants access to every package:** `requires` establishes readability, whereas `exports` controls direct access to a package's public types.
- **Assuming `exports` allows reflection on private members:** `opens` is needed for deep reflection.
- **Using `--add-opens` to fix `IllegalAccessError` on bytecode access:** `--add-opens` is for reflection; direct access requires exporting the appropriate package.
- **Using `--add-exports` to fix `InaccessibleObjectException`:** exporting a package does not grant permission to bypass access checks for private members.
- **Assuming `setAccessible(true)` always succeeds:** since Java 9, JPMS's strong encapsulation can deny the request and throw `InaccessibleObjectException`.
- **Catching `IllegalAccessError` like a checked exception:** this is a linkage `Error`, not `IllegalAccessException`.
- **Confusing an exception from the target method with an access error:** exceptions thrown by an invoked method are usually wrapped in `InvocationTargetException`.

## 8. Diagnostic Checklist

When resolving one of these three errors, check:

- [ ] Accurately identified whether it is `IllegalAccessError`, `IllegalAccessException`, or `InaccessibleObjectException`.
- [ ] Identified the caller module and the module containing the target class or member.
- [ ] Checked `requires` to ensure the caller reads the required module.
- [ ] Checked `exports` if the code needs direct access to a public type.
- [ ] Checked `opens` if a framework needs deep reflection.
- [ ] Chosen the right `--add-exports` or `--add-opens` for the corresponding situation.
- [ ] Verified configuration at both compile time and runtime.
- [ ] Considered using a public API instead of internal reflective access.

Start from the failing operation and the permission that operation requires. When you clearly distinguish bytecode access, normal reflection, and deep reflection, choosing among `exports`, `opens`, `--add-exports`, and `--add-opens` becomes much more accurate while keeping module boundaries clean.