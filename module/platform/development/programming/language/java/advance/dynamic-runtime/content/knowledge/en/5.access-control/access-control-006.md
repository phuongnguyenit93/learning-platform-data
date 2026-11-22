# 5.6 Diagnosing `IllegalAccessException` and `InaccessibleObjectException`

When using Reflection in Java, two similarly named errors often appear at two **different steps**:

- `IllegalAccessException` is a **checked exception**: typically, the program has already found the field, method, or constructor, but **does not have access permission when reading/writing/invoking** it. Typical APIs are `Field.get/set`, `Method.invoke`, `Constructor.newInstance`; `MethodHandles.Lookup` APIs can also report this exception in certain lookup/access situations.
- `InaccessibleObjectException` is an **unchecked exception**, typically occurring when calling `AccessibleObject.setAccessible(true)` to request suppressing access checks, but the **Java Platform Module System (JPMS)** does not allow opening permissions that deeply. This is one of the manifestations of *strong encapsulation* on Java 9+, especially evident from JDK 17 onward.

Both cases can happen on the **same member**: invoking directly without sufficient permission leads to `IllegalAccessException`; trying to force `setAccessible(true)` on a member located in a package that is not `opens` leads to `InaccessibleObjectException`. To handle it properly, you must know **which API raised the error, which class/module the member belongs to, who the caller is, and whether a public API or private reflection is needed**.

Lesson objectives: read stack traces, distinguish errors at the member lookup step from errors at the member usage step, check current access permission using `canAccess`, safely attempt to open access using `trySetAccessible`, understand `exports`/`opens`, and resolve issues using the right Java contract instead of opening permissions indiscriminately.

## 1. Map of Reflection Steps and Error Locations

Let's break a Reflection operation into five steps:

1. **Determine the type:** for example `Class.forName(name)` or `SomeClass.class`.
2. **Find the member:** `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`, `getConstructor`, `getDeclaredConstructor`.
3. **Check accessibility:** read modifiers, `member.canAccess(receiver)`, and if truly necessary, `trySetAccessible()` or `setAccessible(true)`.
4. **Execute:** `Field.get/set`, `Method.invoke`, `Constructor.newInstance`.
5. **Handle errors from the invoked code:** the method/constructor itself may throw an error, usually wrapped by `InvocationTargetException`.

| Symptom | Where it occurs | What to understand |
| --- | --- | --- |
| `NoSuchFieldException` / `NoSuchMethodException` | **Member lookup** step | Could not find the name/signature according to the chosen API; says nothing yet about invocation permission |
| `IllegalAccessException` | **Read/write/invoke** step via Reflection; also in some other lookup APIs | The member exists, but access checks do not allow the caller to use it |
| `trySetAccessible() == false` | **Request to suppress access checks** step | Cannot open deep access under current rules; `false` itself is not an exception |
| `InaccessibleObjectException` | Usually at `setAccessible(true)` | The request to suppress access checks was denied, usually because the named module's package is not open |
| `InvocationTargetException` | After the method/constructor has already been invoked | The body of the method/constructor threw an error; inspect `getCause()` |
| `IllegalArgumentException` | When invoking Reflection with an unsuitable argument/receiver | Not synonymous with missing permission; check argument count/types and receiver |
| `ExceptionInInitializerError` | When the JVM initializes the class | Static initializer failed; cannot be fixed with `setAccessible` |

Therefore, the first action when diagnosing is to **identify the exact line of code that threw the exception**. If `getDeclaredMethod("run")` succeeded but `invoke(target)` threw `IllegalAccessException`, renaming the method or searching for another overload will usually not solve the root cause.

## 2. Access Control in Java Has Multiple Layers

Reflection is simultaneously governed by:

- **Language rules:** `public`, `protected`, package-private (no modifier), `private`; the visibility of the *declaring class* also matters, not just the member's.
- **Relationship between caller and declaring class:** same class, same package, subclass, nestmates, or class in another package. Classes in the same *nest* can access each other's private members under modern Java rules; just because a method is private does not necessarily mean the caller is forbidden.
- **Java Platform Module System (JPMS):** since Java 9, a module can expose its public API via `exports`, while keeping private/package-private implementation closed to reflection if the package does not `opens`.
- **How the application is run:** the classpath usually places application classes into the *unnamed module*; the module-path creates *named modules* with their own descriptors. Permissions between the two modes can differ.
- **Other runtime policies:** such as security checks in environments configured with them; and special rules for certain fields that cannot be modified even if access checks have been suppressed.

### 2.1. Reading only the member's modifiers is not enough

For example, a package-private class containing a `public` method:

```java
package demo.internal;

class InternalService {
    public void execute() {
        System.out.println("executed");
    }
}
```

A caller in another package can find a public method using the appropriate Reflection mechanism, but that does not prove it is allowed to invoke a method of a non-public declaring class. When encountering `IllegalAccessException`, check **both `member.getModifiers()` and `member.getDeclaringClass().getModifiers()`**.

Similarly, if you try to invoke a private constructor from a class without permission, `Constructor.newInstance()` may throw `IllegalAccessException`, even though `getDeclaredConstructor()` already returned the `Constructor` object successfully.

### 2.2. `getMethod` and `getDeclaredMethod` do not grant permission

The following two calls have different meanings:

```java
type.getMethod("work");         // Find matching public method, including inherited public methods
type.getDeclaredMethod("work"); // Find method declared on the class itself, regardless of visibility
```

`getDeclaredMethod` does **not** mean "permitted to invoke private methods". It only allows discovering metadata of declared members. The same applies to `getDeclaredField` and `getDeclaredConstructor`. There is no guarantee that a member returned by `getDeclared...` can be used directly by the caller.

Conversely, `getMethod` finds public members, yet a method of an inaccessible class can still cause an access error upon invocation. Therefore, distinguish between **a member being found** and **a member being invocable**.

## 3. `IllegalAccessException`: member found, but cannot be invoked

Suppose a domain class has a private constructor, field, and method. Run Reflection from a **different top-level class**, not in the same nest, to observe three separate access checks:

Create file **`AccessExceptionDemo.java`** (JDK 17+):

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class SecretBox {
    private final String secret;

    private SecretBox(String secret) {
        this.secret = secret;
    }

    private String reveal() {
        return "value=" + secret;
    }
}

public class AccessExceptionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<SecretBox> ctor =
                SecretBox.class.getDeclaredConstructor(String.class);
        System.out.println("constructor accessible: "
                + ctor.canAccess(null));
        try {
            ctor.newInstance("java");
        } catch (IllegalAccessException e) {
            System.out.println("constructor: IllegalAccessException");
        }

        System.out.println("constructor override: "
                + ctor.trySetAccessible());
        SecretBox box = ctor.newInstance("java");

        Field field = SecretBox.class.getDeclaredField("secret");
        try {
            field.get(box);
        } catch (IllegalAccessException e) {
            System.out.println("field: IllegalAccessException");
        }

        System.out.println("field override: "
                + field.trySetAccessible());
        System.out.println("field value: " + field.get(box));

        Method method = SecretBox.class.getDeclaredMethod("reveal");
        try {
            method.invoke(box);
        } catch (IllegalAccessException e) {
            System.out.println("method: IllegalAccessException");
        }

        System.out.println("method override: "
                + method.trySetAccessible());
        System.out.println("method result: " + method.invoke(box));
    }
}
```

Compile and run on the **standard classpath**, without configuring additional access policies:

```bash
javac --release 17 AccessExceptionDemo.java
java AccessExceptionDemo
```

Stdout:

```text
constructor accessible: false
constructor: IllegalAccessException
constructor override: true
field: IllegalAccessException
field override: true
field value: java
method: IllegalAccessException
method override: true
method result: value=java
```

### Why does the example run this way?

1. `getDeclaredConstructor(String.class)` and `getDeclaredField("secret")` find the **metadata**, even though the members are `private`.
2. `AccessExceptionDemo` and `SecretBox` are **two top-level classes**. They are not nestmates; the caller does not have direct access to private members.
3. `ctor.canAccess(null)` returns `false`; a constructor does not require a receiver object, so the argument to `canAccess` is `null`.
4. Before opening access, `newInstance`, `field.get`, and `method.invoke` throw `IllegalAccessException`; the program catches each case as expected.
5. Both application classes are in the same **unnamed module** on the classpath; suppressing access checks for these private members is permitted. Therefore all three `trySetAccessible()` calls return `true`.
6. Once access suppression is permitted, the calls succeed and print the values as expected.

**Environment note:** The example output is designed for two top-level classes in the same source file and classpath execution on JDK 17+, with no special sandbox/security checks. If the classes are moved into different named modules, the `trySetAccessible` results can change due to `opens` rules.

Do not take a private **nested class** inside `AccessExceptionDemo` as an example and claim it is guaranteed to be denied: classes belonging to the same nest can have private access to one another in Java 11+. That is why some real-world Reflection experiments behave differently from initial intuition.

## 4. `InaccessibleObjectException`: request for deep access denied

Since JPMS, a named module can intentionally **not open a package** to other modules. `setAccessible(true)` only requests suppressing access checks if the module model allows it; it does not bypass all boundaries.

A common example is attempting to access an internal `private` field of a JDK class in `java.base`:

Create file **`ModuleBlockDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class ModuleBlockDemo {
    public static void main(String[] args)
            throws NoSuchFieldException {
        Field field = String.class.getDeclaredField("value");

        System.out.println("declaring module: "
                + field.getDeclaringClass().getModule().getName());
        System.out.println("trySetAccessible: "
                + field.trySetAccessible());

        try {
            field.setAccessible(true);
            System.out.println("setAccessible: succeeded");
        } catch (InaccessibleObjectException e) {
            System.out.println(
                    "setAccessible: InaccessibleObjectException");
        }
    }
}
```

Run on **default OpenJDK 17/21**, without adding any JVM option to open the package:

```bash
javac --release 17 ModuleBlockDemo.java
java ModuleBlockDemo
```

Output in that configuration:

```text
declaring module: java.base
trySetAccessible: false
setAccessible: InaccessibleObjectException
```

The `String.value` field is a **JDK implementation detail used solely for demonstration**, not a stable API for applications to depend on. Other JDK versions/implementations may change internal structures; the goal of this section is the access control model.

Explanation:

- `getDeclaredField("value")` finds the field metadata, but does **not** grant access.
- Package `java.lang` belongs to the named module `java.base` and **does not open deep access by default** to the application's unnamed module.
- `trySetAccessible()` returns `false` in a controlled manner.
- `setAccessible(true)` demands enabling suppression, which is not allowed, so it throws `InaccessibleObjectException` right at that call. Neither `field.get(...)` nor `field.set(...)` has even executed yet.

If you run this experiment alone with the JVM option:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED ModuleBlockDemo
```

Then on the same OpenJDK containing the field above, the output changes to:

```text
declaring module: java.base
trySetAccessible: true
setAccessible: succeeded
```

`--add-opens` here only demonstrates **changing the access check condition**. This is not a recommendation to fix production code by accessing `String.value`; normal applications should use the public API of `String`.

### 4.1. Common error message format

An `InaccessibleObjectException` message may contain text such as:

```text
Unable to make field private final byte[] java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module
```

How to read it: the **target** is the private field `String.value`; the **owning module** is `java.base`; the **package that needs to be opened** is `java.lang`; the **caller module** is the unnamed module. These names help pinpoint exactly where the configuration or design is incompatible. Do not just look at the name `InaccessibleObjectException` and add an overly broad JVM flag.

## 5. How do `canAccess`, `trySetAccessible`, and `setAccessible` differ?

All three are APIs on `AccessibleObject`, the superclass of `Field`, `Method`, and `Constructor`.

| API | Purpose | Result / error | Effect |
| --- | --- | --- | --- |
| `canAccess(receiver)` | Asks whether the **current** caller can access the member through this object | `true`/`false`; wrong receiver may throw `IllegalArgumentException` | Checks only, does not modify state |
| `trySetAccessible()` | Attempts to enable suppression of Java language access checks | `true` if succeeded; `false` when it cannot be enabled due to access/module limits | May change the accessibility state of **this reflection object** |
| `setAccessible(true)` | Requests enabling suppression | Succeeds or throws `InaccessibleObjectException` if not permitted | May change the accessibility state of this object |
| `setAccessible(false)` | Disables previously enabled suppression | Reverts to normal access checks | Does not alter modifiers or class structure |

In both `trySetAccessible` and `setAccessible`, a `SecurityException` can still occur when corresponding security checks are active. Do not assume `trySetAccessible()` can absolutely never throw an exception.

### 5.1. `canAccess` requires the right receiver

- For `Constructor`, `static Field`, `static Method`: call `canAccess(null)`.
- For an instance field/method: pass an object of the declaring class or a suitable subtype, e.g., `field.canAccess(target)`, `method.canAccess(target)`.
- Passing `null` to `canAccess` of an instance field/method or an incompatible receiver can produce `IllegalArgumentException`. That is an **API usage error**, not proof that the member is blocked by JPMS.

`canAccess` reports access from the **caller performing the check**, so moving the code into another class/package/module can change the result. At the same time, `canAccess` on an `AccessibleObject` whose access checks have already been successfully suppressed may return `true`, even when normal Java source code could not write the same access directly.

### 5.2. Choosing how to call when private reflection is unavoidable

Handling pattern inside a method that has a `Field field` and a validated `Object target`:

```java
if (!field.canAccess(target)) {
    if (!field.trySetAccessible()) {
        throw new IllegalStateException(
                "No reflective access to "
                + field.getDeclaringClass().getName()
                + "." + field.getName());
    }
}
Object value = field.get(target);
```

This is an **illustrative snippet, not a standalone program**; the enclosing method needs to handle `IllegalAccessException`, and `target` must match the instance field (or be `null` if it is a static field). `trySetAccessible` lets you fail deliberately and report a clear error when the package is not open. It does not turn every denied permission into a valid value; you should not swallow the error and assign an arbitrary default.

If you only use a **valid public API**, `setAccessible(true)` is usually **not needed**: design or call the proper public member of a public class in an exported package, rather than enabling suppression out of habit.

## 6. JPMS: `exports` vs `opens`

The module descriptor in `module-info.java` describes which packages are exposed to other modules and which packages allow deep Reflection. The difference is the root cause of many errors after upgrading applications to JDK 17+ or migrating from classpath to module-path.

| Configuration in the module owning the package | Compile-time/public API access from another module | Deep reflection into non-public members |
| --- | --- | --- |
| `exports p;` | Allows using public types of package `p`, with appropriate module readability | **Does not automatically allow** bypassing private/package-private access |
| `exports p to m;` | Exports public API only to module `m` | Still **does not automatically open** private reflection |
| `opens p;` | Does not automatically export for importing public types in source | Allows runtime deep reflection from other modules via access APIs |
| `opens p to m;` | Does not automatically export for compile-time | Opens deep reflection for module `m` |
| `open module x { ... }` | Does not automatically export every package | Opens all packages in the module; broad scope |
| Neither `exports` nor `opens` | Public API in that package is not exported to other modules | Disallows deep reflection across modules |

For example, a domain module needs to expose a public API to the application, while allowing only a designated framework to reflect into the implementation:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.serializer;
}
```

Explanation: module `com.example.serializer` is permitted deep reflective access into `com.example.domain.model` if other Reflection conditions are met. Conversely, that module's source code is **not** automatically allowed to `import` public types from `com.example.domain.model` solely because of `opens`.

In the caller's module:

```java
module com.example.serializer {
    requires com.example.domain;
}
```

The two snippets are **two `module-info.java` files in two different modules**, and cannot be placed together in a single Java file. A domain module may contain multiple packages; the package names above are structural examples. You do not need to build an entire modular application to understand the principle of scoped opening.

### 6.1. When is `exports` enough for public reflection?

If the caller needs to invoke a **public method of a public class** in a package exported to the caller (and module readability is valid), public reflection usually works without `opens`. In this situation, trying to call `setAccessible(true)` is unnecessary.

If the caller needs a private field/constructor, or a non-public member, `exports` is **not enough**. Consider a public API/factory; if the framework truly requires deep reflection, configure minimal `opens` for the specific package and specific module.

Note: the fact that the compiler allows referencing a public type does not prove the caller can use every member of the type. Member modifiers and Java rules still apply.

### 6.2. Why `--add-exports` does not fix every error

The two JVM options have different goals:

```text
--add-exports <module>/<package>=<target-modules>
--add-opens   <module>/<package>=<target-modules>
```

- `--add-exports` adds package export permission allowing use of the public API within the target scope; it does not automatically grant deep reflection into private members.
- `--add-opens` adds package open permission allowing deep access via Reflection within the target scope, but does not turn private fields/methods into a public source API.

For example, when the target is a classpath app, the target is usually written as `ALL-UNNAMED`. If the caller is a named module, use the **specific module name**, such as `com.example.serializer`. Do not confuse the package name and the module name on either side of `/`.

In real deployments, prefer fixing the **module descriptor you own**. Only use launch flags as an intentional compatibility measure when you cannot modify the source module, clearly documenting the reason and scope of the opening. For JDK internals, opening modules can cause the application to depend on structures that are not public API.

## 7. Step-by-Step Diagnostic Workflow When an Error Occurs

When you receive a stack trace or issue report, resolve it in the following exact order.

### Step 1 — Name the error and the failing API

Record precisely:

- Target class/member, e.g., `com.example.User#name`, `java.lang.String#value`.
- Failing API: `getDeclaredField`, `Field.get`, `Method.invoke`, `Constructor.newInstance`, `setAccessible`, `trySetAccessible`, or `MethodHandles.privateLookupIn`.
- Full exception type and cause. Do not lump `NoSuchMethodException`, `IllegalAccessException`, `InaccessibleObjectException`, and `InvocationTargetException` under a single label like "Reflection is broken".

If `getDeclaredMethod` throws `NoSuchMethodException`, fix the name/signature and check `getMethod` vs `getDeclaredMethod` first. Do not open modules to fix a method that genuinely does not exist.

### Step 2 — Confirm the actual member and declaring class

`getDeclaringClass()` is the class **that declares the member**, which may differ from the class chosen by the user in configuration. For inherited methods, check which superclass/interface declares the member. Read:

```java
Class<?> owner = method.getDeclaringClass();
String memberModifiers =
        java.lang.reflect.Modifier.toString(method.getModifiers());
String ownerModifiers =
        java.lang.reflect.Modifier.toString(owner.getModifiers());
```

This is an **illustrative snippet** where `method` is an already-found `java.lang.reflect.Method`. If the method is public but the owner is package-private, access behavior differs from a public method of a public class.

### Step 3 — Check the caller and module boundary

Use `Class.getModule()` and `Class.getPackageName()` to learn which module/package the member belongs to. Example reusable diagnostic method in a Java 17+ class:

```java
static void printBoundary(java.lang.reflect.Member member,
                          Class<?> callerClass) {
    Class<?> owner = member.getDeclaringClass();
    Module ownerModule = owner.getModule();
    Module callerModule = callerClass.getModule();
    String packageName = owner.getPackageName();

    System.out.println("declaring class: " + owner.getName());
    System.out.println("member: " + member.getName());
    System.out.println("package: " + packageName);
    System.out.println("owner module: "
            + (ownerModule.isNamed()
                    ? ownerModule.getName() : "<unnamed>"));
    System.out.println("caller module: "
            + (callerModule.isNamed()
                    ? callerModule.getName() : "<unnamed>"));
    System.out.println("exported to caller: "
            + ownerModule.isExported(packageName, callerModule));
    System.out.println("open to caller: "
            + ownerModule.isOpen(packageName, callerModule));
}
```

`Member` is shared by `Field`, `Method`, and `Constructor`. This is an **illustrative method**, which must be placed in a class and called with the actual class containing the application's Reflection code; passing the wrong `callerClass` will produce a misleading description of the module boundary. `isExported` and `isOpen` provide module metadata and do not replace modifier/receiver checks; `trySetAccessible` remains the test of whether access can be opened for a specific member.

When reading a stack trace, distinguish the **module of the library calling Reflection** from the module containing the `main` entrypoint: those two modules may not be the same. If a serializer runs in `com.example.serializer`, the package must be opened to that module, not just to the application module.

### Step 4 — Check receiver and signature

For instance fields/methods, `canAccess(instance)` needs an object of the right type. For static fields/methods or constructors, use `canAccess(null)`. For `Method.invoke` and `Constructor.newInstance`, check parameter types, argument count, primitive unboxing/widening, and special varargs handling.

Do not misinterpret an `IllegalArgumentException` caused by an invalid receiver as `IllegalAccessException`. When a constructor runs and throws a business error, `InvocationTargetException.getCause()` is where to look for the root cause.

### Step 5 — Choose the smallest contract-compliant solution

A reasonable order of priority:

1. Call an existing public API of a public class in a properly exported package.
2. If you own the class: design an appropriate method, constructor, or factory instead of private reflection if that API should be public.
3. If a framework truly needs deep Reflection: open **only the right package to the right module** using `opens ... to ...`.
4. If you do not control the module descriptor: evaluate the `--add-opens` JVM flag with a narrow target in an environment you manage.
5. If the member is a JDK implementation detail or unsupported library internal: switch to a public API/compatible library rather than building a long-term dependency on a private field.
6. If valid permission cannot be granted: fail with a clear configuration message, including the member name and the blocked module/package.

You should not handle it with `catch (Exception ignored)`, return `null`, or fabricate an empty object and let the failure surface elsewhere. Doing so hides the failure location and can cause silent data corruption that is hard to detect.

## 8. When `setAccessible(true)` Does Not Solve `IllegalAccessException`

`setAccessible(true)` is a limited tool, not a universal "permission off switch". Before using it, consider which of the following groups applies:

**Group A — Access check due to modifiers/package within the same module:** `trySetAccessible` can be used within a well-designed framework scope; or better yet, call a public API. The `SecretBox` example from the first program belongs to this group.

**Group B — Named module has not opened the package:** `setAccessible(true)` throws `InaccessibleObjectException`; `trySetAccessible` returns `false`. You need to fix `opens` or stop accessing the private member, rather than repeatedly calling `Field.get`.

**Group C — Not an access error:** constructor does not exist (`NoSuchMethodException`), wrong receiver (`IllegalArgumentException`), target itself throws an error (`InvocationTargetException`), wrong field type, class initialization error. Opening permissions will not make them disappear.

**Group D — Special field write rules:** certain `final` fields (such as record components, hidden classes) have special restrictions; suppressing access checks does not grant permission to mutate all state. Reflection into JDK internals can be unstable across versions. If the design requires changing state, choose a valid domain constructor/method.

**Group E — `MethodHandles` and `privateLookupIn`:** lookup mechanisms have their own access policies; functions like `MethodHandles.privateLookupIn(targetClass, lookup)` require module/readability conditions and appropriate `opens` when crossing modules. It can throw `IllegalAccessException` if permission is lacking. Switching to Method Handles does **not** mean bypassing JPMS.

Understanding the difference between **Java language access** and **actual ability to read/write state** helps avoid solutions that are both dangerous and ineffective.

## 9. Diagnosing Errors When Upgrading Java 8 → 17+

On Java 8, frameworks often attempted `setAccessible(true)` on many internal JDK details. When running on JDK 9+, JPMS introduces module boundaries. JDK 17 enforces stronger encapsulation on JDK internals; relying on "illegal reflective access" that merely produced warnings in earlier releases is no longer the default behavior.

Common signs:

- Stack trace starts at `java.lang.reflect.AccessibleObject.checkCanSetAccessible` or `Field.setAccessible`, followed by `InaccessibleObjectException`.
- Message has the form `module java.base does not "opens java.lang" to ...`, or another package in a named module.
- Application runs on the classpath but fails when moved to the module-path because classes now belong to named modules with explicit descriptors.
- A serialization, ORM, DI, or test framework library tries to read private members of domain classes whose module package has not been `opens`.
- The project has `--add-exports` but is trying to access a private field, leading to confusion because public API export is not equivalent to deep reflection.

How to handle when upgrading: check whether the library version supports the target Java version; read the owner module/package in the error; prefer library versions that use supported APIs; open the right package to the framework module if your domain module intentionally allows Reflection; document JVM flags if they must be used.

Avoid treating mass additions of `--add-opens` as a permanent solution. A closed package usually signals an API boundary that the owning module intends to maintain.

## 10. Pattern for Cause-Preserving Exception Handling in Frameworks

A utility may need to report a standardized configuration error while still preserving the cause. For example, the following method only uses a **public no-arg constructor** and does not suppress access checks:

```java
static <T> T createPublicNoArg(Class<T> type) {
    try {
        return type.getConstructor().newInstance();
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "No public no-arg constructor: " + type.getName(), e);
    } catch (IllegalAccessException e) {
        throw new IllegalStateException(
                "Public constructor inaccessible: " + type.getName(), e);
    } catch (InstantiationException e) {
        throw new IllegalArgumentException(
                "Cannot instantiate type: " + type.getName(), e);
    } catch (java.lang.reflect.InvocationTargetException e) {
        Throwable cause = e.getCause();
        throw new IllegalStateException(
                "Constructor threw exception: " + type.getName(), cause);
    }
}
```

This is an **illustrative method inside a Java 17+ class**, not a standalone program; `type` is a `Class<T>` received from the caller. A public constructor can still be blocked when the declaring class is not public or the module has not exported the corresponding package. The utility does not attempt to call a private constructor and does not swallow exceptions thrown by domain code. In a specialized API, you might want to propagate a `RuntimeException` or `Error` from the target directly instead of wrapping it; the choice depends on the framework's error contract.

For deep reflection operations, you should handle opening access before invoking:

```java
static Object readField(java.lang.reflect.Field field, Object receiver)
        throws IllegalAccessException {
    if (!field.canAccess(receiver) && !field.trySetAccessible()) {
        throw new IllegalStateException(
                "Package not open for reflective field access: "
                + field.getDeclaringClass().getName()
                + "#" + field.getName());
    }
    return field.get(receiver);
}
```

This snippet is **a standalone method in terms of signature, but must be placed inside a class**. `receiver` is an instance of the right type if the field is non-static; pass `null` for a static field. `trySetAccessible()` returns `false` when suppression cannot be enabled, so the message should only describe missing reflection permission in general; another cause such as security checks can still arise separately. Before using this on untrusted input, you must restrict the set of types/members the framework is allowed to access, because opening reflection to private state is not safe behavior by default.

## 11. Confusions That Cause Misdiagnosis

### 11.1. Confusing `IllegalAccessException` with `IllegalAccessError`

`IllegalAccessException` is a **checked exception** commonly seen from Reflection APIs. `IllegalAccessError` is a **`LinkageError`**, which can occur when bytecode/linkage attempts to access a class or member that is not permitted by runtime structure, such as after a binary compatibility change. The two names look similar, but their causes, checking paths, and handling differ. Do not catch `IllegalAccessException` and assume you have covered `IllegalAccessError`.

### 11.2. Confusing `InvocationTargetException` with a permission error

When `Method.invoke` or `Constructor.newInstance` actually succeeds in invoking the target, any exception raised by the **body of the target** is wrapped in `InvocationTargetException`. For example, if the body throws `IllegalStateException`, it is not a permission error. Inspect `getCause()` and the original stack trace.

In the rare case where the target itself tries to open reflection into another module and throws `InaccessibleObjectException`, it can appear **inside the cause of `InvocationTargetException`**, because here the error comes from the target's code, unlike a direct error at the caller's `setAccessible` call. Therefore, you must read the entire `cause` chain.

### 11.3. Confusing "can be found" with "allowed to use"

`getDeclaredField`, `getDeclaredMethod`, and `getDeclaredConstructor` can return metadata for private members. It is the invoke/get/set step that requires an additional access check. Do not rely on the existence of a `Field` to conclude that permission has been granted.

### 11.4. Confusing "same package" with "same module"

A Java package is a namespace; a module is a different boundary layer. A caller can use a familiar package name yet still belong to a different named module, and open/export is checked against the **actual modules**. When multiple class loaders exist, the same class name is also not enough to guarantee the same runtime type; check the declaring class, loader, and module of the actual object.

### 11.5. Confusing `opens` with a permanent public API

`opens` grants deep reflection permission at runtime; it does **not** create an API guaranteed by the compiler to remain compatible. If a framework accesses a private field, renaming the field between releases will still break the code. Public methods/factories with clear contracts are generally more durable.

### 11.6. Confusing `trySetAccessible(false)` with a permanent state

`trySetAccessible()` may return `false` in the current runtime because the module is not open, yet when the module descriptor or launcher flags are legitimately changed, the result can be different. Do not cache that conclusion across all class loaders, deployments, or JDK versions.

### 11.7. Confusing `setAccessible(true)` with modifying modifiers

It does not turn a field into `public` or modify the class file; it requests suppressing Java language access checks for that specific Reflection object according to runtime rules. That does not mean every other object or every caller has the same permission.

## 12. Quick Decision Table by Stack Trace

| First notable failure point | Priority investigation direction | Appropriate fix |
| --- | --- | --- |
| `Class.getDeclaredMethod` / `getDeclaredField` throws `NoSuch...` | Name, signature, declaring class, declared vs inherited API | Choose the right member that actually exists |
| `Method.invoke` throws `IllegalAccessException` | Method + declaring class modifiers; caller; module exports | Call public API or configure visibility properly |
| `Constructor.newInstance` throws `IllegalAccessException` | Constructor visibility, class visibility, module boundary | Use public constructor/factory; controlled deep reflection |
| `Field.get/set` throws `IllegalAccessException` | Private/package-private field, receiver, class, and module | Access via accessor or open permission legitimately |
| `trySetAccessible()` returns `false` | Owner module/package and caller module | Need properly scoped `opens` or change API |
| `setAccessible(true)` throws `InaccessibleObjectException` | Message `does not "opens ..."` | Fix JPMS `opens`, narrow JVM flag, or remove private reflection |
| `Method.invoke` throws `InvocationTargetException` | `getCause()` of target | Fix method logic or input; preserve cause |
| `newInstance` throws `InstantiationException` | Abstract class or non-instantiable type | Use a concrete implementation |
| `canAccess` throws `IllegalArgumentException` | Null/wrong-type receiver | Supply the right receiver or `null` for static/constructor |

The table is an investigation guide, not a substitute for checking actual context. The exception name is only the starting point; the stack trace, specific class/module, and API contract determine where to fix it.

## 13. Tests Needed After Fixing

You should verify on the **actual target JDK and execution mode** (classpath or module-path), not only in the IDE. Useful cases:

- Public class + public member in an exported package: invocable without suppressing access checks.
- Private member in the same unnamed module: `trySetAccessible` is permitted if there are no additional policies, though this is not a reason to use private APIs arbitrarily.
- Private member of another named module whose package is **not** `opens`: `trySetAccessible` returns `false`, `setAccessible(true)` throws `InaccessibleObjectException`.
- Named module explicitly `opens p to caller.module`: deep reflection by the caller is permitted within the opened scope, provided other conditions hold.
- Public member whose declaring class is not accessible: verify `IllegalAccessException` and a clear message.
- Target method/constructor throws an error: the framework must identify `InvocationTargetException.getCause()`, not misattribute it as "access denied".
- Static and instance members: correct receiver for `canAccess`/invoke/get.
- Run with and without `--add-opens` in an **isolated test**, ensuring the flag only takes effect where explicitly configured.

When a test passes on the classpath but fails on the module-path, record `java --version`, the modules containing the target and caller, the package that needs to be opened, and the full launch command along with the list of flags. That information is more valuable than capturing just a single line of the exception.

## 14. Practice Scenarios

### Scenario A — Serializer cannot read a model's private field

A serializer uses `modelClass.getDeclaredFields()`, followed by `field.setAccessible(true)`. The model is in module `com.acme.domain`, package `com.acme.model`, and the serializer is in `com.acme.serializer`. The exception states that the domain module does not `opens` the model package.

**Diagnosis:** the member was found; it was blocked at **deep access opening** due to the module boundary, so this is a classic `InaccessibleObjectException`.

**Fix:** if the serializer requires deep reflection by contract, add to the domain descriptor:

```java
opens com.acme.model to com.acme.serializer;
```

This line must be inside `module com.acme.domain { ... }`; the example only illustrates the added directive, **not a complete `module-info.java` file**. If you do not want to expose private structure, provide public properties/getters and configure the serializer to use that API.

### Scenario B — Test invokes a private method when access cannot be suppressed

A test calls `getDeclaredMethod("compute")` successfully, but `trySetAccessible()` returns `false`. The class is in a package not opened from the module under test to the test module.

**Diagnosis:** not `NoSuchMethodException`; nor was the method "lost" by the compiler. Module policy is blocking private reflection.

**Fix:** test through the public contract if sufficient; if the test framework truly needs to reflect on private members, open the specific package to the test module in the test configuration or via a launch option applied only to the test environment. Do not sneak a global flag into production.

### Scenario C — Public method exists yet `IllegalAccessException` still occurs

A caller uses Reflection to invoke a public method of a package-private declaring class from another package.

**Diagnosis:** the method being public is not enough; you must consider the accessibility of the declaring class, as well as the package and module. If the caller cannot access the class, `Method.invoke` can be denied.

**Fix:** define an exported public interface or public facade; invoke through the public contract. Try `setAccessible(true)` only when there is a genuine reason to access the implementation, within what the module permits.

### Scenario D — Java upgrade and error with `java.lang.String.value`

An application or legacy library uses private fields of `String`. When upgrading to Java 17, the message `java.base does not "opens java.lang"` appears.

**Diagnosis:** dependency on a JDK internal detail protected by strong encapsulation. This is a sign to change the integration, not just tweak Reflection syntax.

**Fix:** use the public `String` API or upgrade the library to a compatible version. Depending on short-term compatibility requirements, you may evaluate `--add-opens java.base/java.lang=ALL-UNNAMED` in controlled testing; do not treat it as a stable production solution.

## 15. Self-Check Questions

**Question 1.** `getDeclaredField("secret")` succeeds; `field.get(instance)` throws `IllegalAccessException`. Is the field name wrong?

**Answer:** No. The lookup found the field; the error occurred when accessing the value. You need to inspect the modifiers, declaring class, caller, module permissions, and accessibility state of the `Field` object.

**Question 2.** `field.trySetAccessible()` returns `false`; if you call `field.setAccessible(true)` in the same context, what error might occur?

**Answer:** When the cause is that the module does not allow suppressing access checks, `setAccessible(true)` throws `InaccessibleObjectException`. `trySetAccessible` returns `false` so the caller can handle the case where access is not granted.

**Question 3.** The domain module has `exports com.acme.model;`, but a framework needs to read a private field. Is `exports` enough?

**Answer:** No. `exports` allows using the public API in the package; deep reflection from another module usually requires `opens com.acme.model to <framework-module-name>;` or switching to a public accessor/factory.

**Question 4.** `Method.invoke` throws `InvocationTargetException`, with cause `IllegalStateException`. Is this a permission error or a logic error?

**Answer:** The method was invoked and the target itself threw `IllegalStateException`. Diagnose the logic/input inside the target and preserve the cause; do not change `opens` without reason.

**Question 5.** For an instance `Method`, calling `method.canAccess(null)` produces `IllegalArgumentException`. Is `setAccessible(true)` a reasonable fix?

**Answer:** No. `canAccess` requires a suitable receiver instance for a non-static method. Pass an object of the right type, and only then check whether access permission is actually missing.

**Question 6.** A class in the same package but not in the same nest invokes a private constructor via `Constructor.newInstance` without access suppression. What is the typical exception?

**Answer:** `IllegalAccessException` because the private constructor is inaccessible. Whether `trySetAccessible` succeeds depends on runtime module/access relationships; do not infer it from lookup succeeding.

**Question 7.** An app running on the classpath can private-reflect on its own classes, but gets blocked when switched to named modules. What is the first investigation step?

**Answer:** Check the declaring module/package, caller module, module descriptor, and corresponding `opens` permissions. Do not automatically change all fields to public.

**Question 8.** Can `MethodHandles.privateLookupIn` be used to bypass `opens`?

**Answer:** No. This API still obeys JPMS access rules and can throw `IllegalAccessException` if the lookup does not meet the requirements. Method Handles are not a mechanism to bypass module encapsulation.

## Official References

- Java SE 21, `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html — `canAccess`, `trySetAccessible`, `setAccessible`, and module conditions.
- Java SE 21, `InaccessibleObjectException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html — exception type when accessibility cannot be enabled.
- Java SE 21, `IllegalAccessException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/IllegalAccessException.html — checked exception for invalid access behavior.
- Java SE 21, `Module`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html — `isExported` and `isOpen`.
- Java SE 21, `Method`/`Field`/`Constructor`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html ; https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html ; https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html .
- Java Language Specification 21, §6.6 Access Control: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.6 .
- Java Platform Module System (JEP 261) and Strongly Encapsulate JDK Internals (JEP 403): https://openjdk.org/jeps/261 ; https://openjdk.org/jeps/403 .