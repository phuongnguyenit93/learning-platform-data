# Why Not Use the Obsolete `Class.newInstance()`?

## 1. Learning Objectives

When learning Reflection, we often encounter a snippet creating an object by class name:

```java
Class<?> type = Class.forName("com.example.Plugin");
Object instance = type.newInstance();
```

The `Class.newInstance()` call on the second line **has been marked deprecated since Java 9**. Java 17 still keeps this method for legacy compatibility, yet new code should use `Constructor<T>.newInstance(...)` through a `java.lang.reflect.Constructor<T>` object.

The core issue is not merely the deprecation warning. `Class.newInstance()` has three major limitations:

1. **Only calls the no-argument constructor**; there is no way to pass initialization parameters.
2. **Can directly propagate checked exceptions from the constructor**, even though `Class.newInstance()`'s signature does not declare those exceptions. This is a compile-time exception-checking safety issue.
3. **Does not allow managing a specific constructor**: it is hard to inspect signatures, parameter types, annotations, modifiers, and evaluate access to non-public constructors. The `Constructor` API expresses the process of finding, checking permissions, and then invoking a constructor more clearly.

Basic replacement according to Java 17 documentation:

```java
T object = clazz.getDeclaredConstructor().newInstance();
```

Here `clazz` has type `Class<T>`. `getDeclaredConstructor()` looks up the no-argument constructor **declared by the class itself**, and `newInstance()` actually creates the instance. You must handle `NoSuchMethodException` and `InvocationTargetException` along with other Reflection errors that may arise. Do not interpret the replacement snippet as opening access to every private constructor; access issues must still be handled separately.

## 2. What Does `Class.newInstance()` Actually Do?

Signature of the legacy method:

```java
@Deprecated(since = "9")
public T newInstance()
        throws InstantiationException, IllegalAccessException
```

`Class<T>.newInstance()` attempts to create an object of the class represented by `Class<T>` via a **no-argument constructor** accessible from the caller. If the class has not yet been initialized, the call triggers class initialization when necessary.

Points to remember:

- `Class.newInstance()` **is not** `Constructor.newInstance()`. The two methods share a name yet belong to different types and have different exception rules.
- You cannot pass a name, id, service, configuration, or other constructor arguments into `Class.newInstance()`.
- If the class lacks an appropriate no-argument constructor, the legacy method typically throws `InstantiationException`. With the modern API, a missing constructor during lookup is clearly represented by `NoSuchMethodException`.
- If the class or constructor is inaccessible, the legacy method may throw `IllegalAccessException`.
- If the constructor itself throws a checked exception, the legacy method **directly propagates that exception** even though its signature declares only the two checked exception types above.

`@Deprecated(since = "9")` is a notice that **this API should no longer be used in new code**. Deprecated does not mean it has been removed from JDK 17, nor does it mean all legacy calls fail immediately. Still, new code should use the approach recommended by Java SE.

## 3. Most Serious Issue: Bypassing Checked Exception Checking

### 3.1. Ordinary Checked Exceptions

Java requires code to handle or declare checked exceptions that the compiler recognizes from method and constructor signatures.

Example of a valid constructor:

```java
import java.io.IOException;

class Loader {
    public Loader() throws IOException {
        throw new IOException("resource unavailable");
    }
}
```

A direct call `new Loader()` requires the caller to handle or declare `IOException`. This is an important safeguard: the compiler forces the program to acknowledge that object creation can fail due to I/O.

### 3.2. Flaw of the Legacy Method

Suppose the following code runs with `Class<Loader>`:

```java
@SuppressWarnings("deprecation")
static Loader legacyCreate()
        throws InstantiationException, IllegalAccessException {
    return Loader.class.newInstance();
}
```

**This is an illustrative example that must be paired with the `Loader` declaration above.** It compiles without catching or declaring `throws IOException`, because the compiler only sees `Class.newInstance()`'s signature declaring `InstantiationException` and `IllegalAccessException`.

When the constructor executes and throws `IOException`, `Class.newInstance()` can propagate that exact exception object outward. That means at runtime it can throw **`IOException` without `legacyCreate()` declaring it**.

The result is not `InvocationTargetException`. This exact behavior lets code bypass Java's checked exception checking mechanism. It makes the error contract of factories/helpers unpredictable and confusing when reading code.

A testing note: if you want to directly demonstrate exception propagation from legacy code, you can use `catch (Exception e)` or handle `Throwable` at an appropriate level; the compiler may reject a `catch (IOException e)` placed around a call whose signature does not declare `IOException`, if no other operation in the `try` block is declared to throw `IOException`.

### 3.3. How Does the New API Solve This?

`Constructor.newInstance(...)` has a clearer contract: **exceptions thrown by the target constructor itself are wrapped in `InvocationTargetException`**.

```java
Constructor<Loader> constructor = Loader.class.getDeclaredConstructor();

try {
    Loader loader = constructor.newInstance();
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // original is IOException("resource unavailable")
}
```

This example snippet requires importing `java.lang.reflect.Constructor`, `InvocationTargetException`, and `Loader` above; other checked exceptions from lookup/instantiation still need to be handled or declared.

As a result, the caller can distinguish two categories of errors:

- **Reflection failed to find/was not permitted/could not create the object**: exceptions belonging to the Reflection layer.
- **The constructor ran, yet constructor logic itself failed**: `InvocationTargetException`, where `getCause()` holds the original error.

`InvocationTargetException` is a checked exception, so the compiler forces the caller to handle or declare it. This is a direct improvement in API contract safety.

## 4. Comparing `Class.newInstance()` and `Constructor.newInstance()`

| Criterion | `Class.newInstance()` (deprecated) | `Constructor.newInstance(args...)` |
|---|---|---|
| Starting point | `Class<T>` object | `Constructor<T>` object |
| Since Java 9 | Marked `@Deprecated` | Recommended API for instantiation via Reflection |
| Supported constructors | Only no-argument constructor | Constructor chosen by **signature**, with or without parameters |
| Selecting overloaded constructor | No | Yes, via `getConstructor` / `getDeclaredConstructor` with exact `Class<?>...` |
| Inspecting constructor metadata | Not via a separate constructor object | Has `getParameterTypes()`, `getModifiers()`, `getAnnotations()`, `isVarArgs()` ... |
| Non-public constructor | Needs constructor accessible in caller context; no object to request suppression | Can find via `getDeclaredConstructor` then check `canAccess`, `trySetAccessible` within module limits |
| Exception from constructor | Propagated directly, including checked exceptions | Wrapped in `InvocationTargetException` |
| Missing no-argument constructor | Typically `InstantiationException` | `getDeclaredConstructor()` throws `NoSuchMethodException` |
| When does constructor execute? | Immediately inside `Class.newInstance()` | When calling `Constructor.newInstance()`, after the lookup step |

The right-hand column **does not promise** every constructor is permitted to be called. Abstract types, enums, class initialization errors, wrong arguments, module permissions, and other runtime conditions still apply.

## 5. Replacement Patterns Tailored to Each Need

### 5.1. Creating an Object with a No-Argument Constructor

If you know the class has a public no-arg constructor:

```java
Class<MyService> type = MyService.class;

// Old (do not keep writing):
// MyService service = type.newInstance();

// New:
MyService service = type.getDeclaredConstructor().newInstance();
```

This is an illustrative snippet in a context with class `MyService` and checked exception handling; not a standalone runnable file.

`getDeclaredConstructor()` finds a no-argument constructor **even if private**. It only returns metadata; invocation may still be blocked. When intending to support only **public constructors**, use:

```java
MyService service = type.getConstructor().newInstance();
```

`getConstructor()` finds only public constructors, whereas `getDeclaredConstructor()` finds constructors at all access levels. **Do not automatically enable `setAccessible(true)` for every constructor** when migrating APIs.

### 5.2. Creating an Object with a Parameterized Constructor

`Class.newInstance()` cannot handle this scenario. For constructor `public Worker(String name, int retries)`:

```java
Constructor<Worker> constructor =
        Worker.class.getConstructor(String.class, int.class);

Worker worker = constructor.newInstance("report", 3);
```

This snippet requires declaring `Worker` and importing `Constructor` in the usage context.

When looking up a constructor, parameter types must **match the exact signature**. For example, `int.class` differs from `Integer.class`. Select the exact constructor before invoking, instead of expecting `getConstructor` to pick an overload based on runtime arguments. When executing `Constructor.newInstance`, Java supports certain valid argument conversions, yet this does not make `getConstructor` change its signature lookup rules.

### 5.3. Private Constructors and Module Checks

Some frameworks need to create instances via non-public constructors. When the design genuinely requires this, do so conditionally:

```java
Constructor<SecretConfig> ctor =
        SecretConfig.class.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalStateException(
            "Constructor is not permitted to open Reflection access");
}

SecretConfig instance = ctor.newInstance("configured");
```

This snippet requires `SecretConfig` to be defined and checked exceptions handled; it is not a standalone program. For constructors, the receiver for `canAccess` is always `null`.

`trySetAccessible()` can return `false` when the module containing the target class does not open the corresponding package. `setAccessible(true)` can throw `InaccessibleObjectException`. The fact that `getDeclaredConstructor` finds a private constructor **does not** mean you are already permitted to use it.

For ordinary applications, a public factory method, constructor injection, or dependency injection is easier to maintain than manually bypassing private access checks.

### 5.4. Creating by a Type Chosen at Runtime

When receiving a `Class<? extends Handler>` from a trusted registry:

```java
static Handler create(Class<? extends Handler> implementation)
        throws ReflectiveOperationException {
    return implementation.getDeclaredConstructor().newInstance();
}
```

This method requires `Handler`/implementation definitions in the project. It illustrates preserving the return type without unchecked casts. If the class is known at compile time, prefer `new`, constructor references, or factories over Reflection.

For class names or inputs from untrusted sources, do not automatically allow instantiating arbitrary classes solely from a string. Maintain a whitelist/registry of valid implementations, verify they implement the expected interface, and use only constructors belonging to the allowed contract.

## 6. Runnable Java 17+ Program: Comparing Legacy and New Behavior

The following example verifies four scenarios in a single file:

1. Creating via a public no-arg constructor with the new API.
2. Missing no-arg constructor while having a parameterized constructor.
3. Constructor throwing checked `IOException`: new API wraps the error, legacy API propagates it directly.
4. Private constructor: looking up metadata with `getDeclaredConstructor`, checking, and requesting controlled access opening.

### 6.1. Full Source Code

Save to the file **`ConstructorMigrationDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorMigrationDemo {
    public static class Basic {
        public Basic() {}
        @Override public String toString() { return "basic"; }
    }

    public static class NeedsArgument {
        private final String value;
        public NeedsArgument(String value) { this.value = value; }
        public String value() { return value; }
    }

    public static class Exploding {
        public Exploding() throws IOException {
            throw new IOException("disk unavailable");
        }
    }

    @SuppressWarnings("deprecation")
    static <T> T oldCreate(Class<T> type)
            throws InstantiationException, IllegalAccessException {
        return type.newInstance();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Basic basic = Basic.class.getDeclaredConstructor().newInstance();
        System.out.println("zero-arg: " + basic);

        try {
            NeedsArgument.class.getDeclaredConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("missing zero-arg: " + e.getClass().getSimpleName());
        }

        NeedsArgument withArg = NeedsArgument.class
                .getDeclaredConstructor(String.class)
                .newInstance("alpha");
        System.out.println("with-arg: " + withArg.value());

        try {
            Exploding.class.getDeclaredConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("modern error: " + e.getClass().getSimpleName());
            System.out.println("root cause: " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        try {
            oldCreate(Exploding.class);
        } catch (Exception e) {
            System.out.println("legacy error: " + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
        }

        Constructor<LockedWidget> locked =
                LockedWidget.class.getDeclaredConstructor(String.class);
        System.out.println("private canAccess: " + locked.canAccess(null));
        boolean opened = locked.trySetAccessible();
        System.out.println("private opened: " + opened);
        if (opened) {
            LockedWidget widget = locked.newInstance("secret");
            System.out.println("private created: " + widget.code());
        }
    }
}

class LockedWidget {
    private final String code;
    private LockedWidget(String code) { this.code = code; }
    public String code() { return code; }
}
```

In the program, `LockedWidget` is a **separate top-level class**, not in the same nest as `ConstructorMigrationDemo`. Because the constructor is private, `locked.canAccess(null)` initially returns `false`. Classes in the same file belong to the unnamed module when run on the classpath; in an ordinary illustrative environment, `trySetAccessible()` is allowed to open access. If moved to named modules with `opens` constraints, behavior can differ.

Legacy code appears **intentionally to illustrate the exception difference**, with `@SuppressWarnings("deprecation")` only on the `oldCreate` helper. Do not use this helper in new production code.

### 6.2. Compiling and Running

Use JDK 17 or later in the directory containing the file:

```bash
javac --release 17 ConstructorMigrationDemo.java
java ConstructorMigrationDemo
```

Verified output when compiled with `--release 17` and run on OpenJDK 21:

```text
zero-arg: basic
missing zero-arg: NoSuchMethodException
with-arg: alpha
modern error: InvocationTargetException
root cause: IOException: disk unavailable
legacy error: IOException: disk unavailable
private canAccess: false
private opened: true
private created: secret
```

### 6.3. Output Explanation

- `Basic.class.getDeclaredConstructor().newInstance()` creates a valid object via the public no-arg constructor.
- `NeedsArgument` only has a constructor taking `String`, so parameterless `getDeclaredConstructor()` throws `NoSuchMethodException`; looking up with `String.class` then instantiates successfully.
- `Exploding` throws `IOException("disk unavailable")` directly inside its constructor. `Constructor.newInstance()` reports `InvocationTargetException`; `getCause()` confirms `IOException` is the root error.
- `oldCreate(Exploding.class)` uses the deprecated API and actually throws **`IOException` directly**, even though `oldCreate`'s signature only declares `InstantiationException` and `IllegalAccessException`.
- `LockedWidget` has a private constructor. `getDeclaredConstructor(String.class)` retrieves the metadata; `canAccess(null)` indicates it is not yet accessible; `trySetAccessible()` succeeds in the example environment, and then `newInstance("secret")` creates the object.

The most important point demonstrated: **the new API separates finding a constructor from calling a constructor, clarifies where errors originate, and wraps exceptions thrown by the executing constructor.**

## 7. Catching Errors and Converting Exceptions Appropriately

The following snippet is a reusable helper that creates objects using a no-argument constructor:

```java
import java.lang.reflect.InvocationTargetException;

public final class Constructors {
    private Constructors() {}

    public static <T> T create(Class<T> type) {
        try {
            return type.getDeclaredConstructor().newInstance();
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Missing no-argument constructor: " + type.getName(), e);
        } catch (InvocationTargetException e) {
            throw new IllegalStateException(
                    "Constructor of " + type.getName() + " failed",
                    e.getCause());
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException(
                    "Cannot instantiate: " + type.getName(), e);
        }
    }
}
```

This is a **compilable Java utility class**, without its own `main`. Calling code invokes `Constructors.create(MyType.class)` when the target class has a valid zero-arg constructor. This helper intentionally **does not open private constructors**, and may fail if the class/method is inaccessible under Java/module rules.

This catch structure distinguishes:

1. `NoSuchMethodException`: the required constructor was not found.
2. `InvocationTargetException`: the constructor ran and threw an error; forward the root error via `getCause()`.
3. Other `ReflectiveOperationException` errors such as `IllegalAccessException`, `InstantiationException`: instantiation was blocked by permissions or type properties.

The wrapping policy like `IllegalArgumentException`/`IllegalStateException` in the helper is an **application choice**, not something mandated by Java Reflection. If callers need to handle root errors individually by type, preserve checked exceptions or declare a domain exception with `cause`. Do not swallow errors or merely log and return `null`, as that hides failed instantiation.

`InvocationTargetException` is not the only exception you may encounter. An error from **class initialization** can surface as `ExceptionInInitializerError`; other Java `Error`s also do not belong to `ReflectiveOperationException` and must be evaluated per application policy.

## 8. No Default Constructor? Don't Guess

This is a common mistake when migrating legacy code:

```java
class Job {
    Job(String id) {
    }
}
```

Because `Job` declares a parameterized constructor, the compiler **does not generate** a no-arg constructor. Result:

```java
Job.class.getDeclaredConstructor(); // NoSuchMethodException
```

Do not "fix" this by adding an empty constructor if the domain requires `id`. Explicitly specify the constructor you intend to call:

```java
Job job = Job.class
        .getDeclaredConstructor(String.class)
        .newInstance("J-001");
```

The two `Job` snippets above serve as brief illustrations in the same context and require catching/declaring checked exceptions when run in practice.

### 8.1. Implicit Constructors and Access Scope

If a class declares no constructors at all, the compiler may provide a no-arg **default constructor** according to Java rules. However, constructor access level and class accessibility still must be considered. A package-private class does not automatically become public merely because a default constructor exists.

Do not use `Class.newInstance()` to guess whether a class can be instantiated. Use `getDeclaredConstructor(...)` to identify the exact signature, verify permissions, and handle outcomes explicitly.

### 8.2. Records, Enums, and Special Classes

- **Records with components:** the canonical constructor typically takes the components in exact type and order. One cannot assume a no-arg constructor exists. A valid delegating no-argument constructor may be added in certain designs, yet it does not exist automatically.
- **Enums:** cannot arbitrarily create additional enum constants via `Constructor.newInstance`; Reflection has specific restrictions and will throw an appropriate error.
- **Abstract classes/interfaces:** cannot be instantiated directly via Reflection constructors.
- **Non-static inner classes:** bytecode-level constructors typically require an extra enclosing instance argument; the reflected signature must be understood accurately. `Class.newInstance()` does not support passing an enclosing instance.
- **Array or primitive `Class`:** not instantiated like ordinary class instances via Reflection constructors; for arrays, use appropriate mechanisms such as `java.lang.reflect.Array.newInstance` when genuinely needed.

A good dynamic instantiation API must have a clear contract regarding **which types are allowed to be created**, **which constructors are supported**, **which parameters are valid**, and **which exceptions are returned**.

## 9. Exception Handling Table When Using the Modern Approach

| Case | Typical step | Result |
|---|---|---|
| No constructor with exact parameter types exists | `getDeclaredConstructor(...)` | `NoSuchMethodException` |
| Constructor exists yet caller lacks permission to invoke | `constructor.newInstance(...)` | `IllegalAccessException` |
| Attempting deep reflection across an unopened package | `setAccessible(true)` / `trySetAccessible()` | May hit `InaccessibleObjectException` / return `false` |
| Missing, extra, or wrongly typed arguments at invocation time | `constructor.newInstance(args...)` | `IllegalArgumentException` |
| Target is abstract, cannot be instantiated | `constructor.newInstance(...)` | `InstantiationException` |
| Target constructor itself throws an error | `constructor.newInstance(...)` | `InvocationTargetException`, root cause in `getCause()` |
| Class initialization fails | Before or during constructor execution | `ExceptionInInitializerError` |
| Attempting to create an enum via Reflection constructor | `constructor.newInstance(...)` | `IllegalArgumentException` |
| Access control in restricted environments | Lookup or operation | Possible `SecurityException` |

Note: class loader/linkage errors or module access errors can occur from the `Class` lookup step or during class loading; the table does not aim to list every JVM `Error`.

`ReflectiveOperationException` is a useful common superclass for many **checked exceptions** such as `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, and `InvocationTargetException`; it does not cover `IllegalArgumentException`, `InaccessibleObjectException`, or `ExceptionInInitializerError`.

## 10. Common Mistakes When Migrating Legacy Code

**Mistake 1: Renaming the API while keeping the same exception catches.** After switching to `getDeclaredConstructor().newInstance()`, you must also handle `NoSuchMethodException` and `InvocationTargetException`. If omitted, code either fails to compile or loses the root cause from the target constructor.

**Mistake 2: Catching `Exception` and reporting "constructor does not exist".** `NoSuchMethodException` differs from `IllegalAccessException` and from `InvocationTargetException`. Classify errors at the right step.

**Mistake 3: Thinking `Class.newInstance()` was deprecated only for "old syntax".** The direct propagation of checked exceptions is an essential technical flaw, not merely a method rename.

**Mistake 4: Assuming `getDeclaredConstructor()` grants permission to call a private constructor.** This API finds private constructors as well, yet does not automatically grant access. Enabling suppression is also constrained by module opens and caller context.

**Mistake 5: Automatically calling `setAccessible(true)` on every class.** This violates design boundaries and can fail with JPMS. If a public contract is needed, prefer `getConstructor(...)`, public factories, or DI.

**Mistake 6: Passing wrong lookup types.** `getDeclaredConstructor(int.class)` differs from `getDeclaredConstructor(Integer.class)`; both count and order of parameter types matter.

**Mistake 7: Using Reflection when unnecessary.** If the type is known at compile time, `new Widget(...)`, `Widget::new`, or `Supplier<Widget>` is clearer, has compile-time type checking, and requires no Reflection error handling.

**Mistake 8: Expanding type scope arbitrarily from external data.** Instantiating classes by name or class loader from untrusted input can trigger constructors/static initializers with side effects. Use a whitelist/registry of permitted implementations.

**Mistake 9: Using a zero-arg helper for records/classes that only have parameterized constructors.** Identify the domain-appropriate constructor and build the object with required arguments, instead of assuming every class has a default constructor.

## 11. Choosing an Appropriate Instantiation Approach

| Context | Preferred approach | Reason |
|---|---|---|
| Type/constructor known at compile time | `new SomeType(args)` | Clear, checked by compiler |
| Want to pass object-creation behavior | `Supplier<T>` or constructor reference | Preserves type safety, avoids Reflection |
| Class selected from runtime registry/plugin | `getConstructor(...)` / `getDeclaredConstructor(...)` + `Constructor.newInstance(...)` | Supports parameterized constructors, metadata, and error control |
| Need non-public constructor access for framework | `getDeclaredConstructor` then explicit permission check | Respects Java access and JPMS |
| Application uses Spring/DI container | Appropriate container/factory mechanism | Reduces coupling to private constructor details |
| Legacy code using `Class.newInstance()` | Migrate to `Constructor.newInstance()` | Avoids deprecated API and checked-exception bypass |

### Checklist When Updating Existing Code

1. Locate actual `Class.newInstance()` calls, not confusing them with `Constructor.newInstance()`.
2. Identify the target class and required constructor signature. If no no-arg constructor exists, select the overload matching the design.
3. Use `getConstructor(...)` when supporting only public constructors; use `getDeclaredConstructor(...)` when there is reason to consider all access levels.
4. Verify access/JPMS permissions before requesting deep reflection.
5. Update error handling: distinguish lookup, access, instantiation, arguments, and exceptions thrown by the target constructor.
6. For `InvocationTargetException`, preserve the original cause via `getCause()` (or `getTargetException()`).
7. Test edge cases: missing matching constructor signature, private constructor, constructor throwing checked exception, abstract class, invalid arguments.
8. Remove old `@SuppressWarnings("deprecation")` if no deprecated API is called anymore; do not leave redundant suppression hiding other warnings.

## 12. Self-Check Questions

1. Why was `Class.newInstance()` deprecated since Java 9 even though it still exists in Java 17?
2. Why can constructor `Loader() throws IOException` cause `Class.newInstance()` to directly throw `IOException` without the caller declaring it?
3. Errors from which stage does `InvocationTargetException` help distinguish? How do you obtain the root cause?
4. How do `getConstructor` and `getDeclaredConstructor` differ in visibility scope?
5. For `Worker(String, int)`, why does parameterless `getDeclaredConstructor()` fail? Write the correct signature.
6. Does `trySetAccessible()` guarantee access to a private constructor of another named module?
7. When should you use `new` or `Supplier` instead of both Reflection forms?
8. Why does switching from `Class.newInstance()` to `getDeclaredConstructor().newInstance()` require reviewing `catch`/`throws`?

**Key takeaway:** Use `Constructor.newInstance(...)` when dynamic instantiation via Reflection is genuinely needed. It allows selecting parameterized constructors, checking metadata and permissions explicitly, and **wraps exceptions thrown by the constructor in `InvocationTargetException`**. `Class.newInstance()` has been deprecated since Java 9, supports only no-argument constructors, and can bypass the compiler's checked-exception checks.

Official references: [Java SE 17 — `Class.newInstance()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#newInstance()), [`Class.getDeclaredConstructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredConstructor(java.lang.Class...)), [`Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)), [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).
