# 3.4 Creating Objects with `Constructor.newInstance` and Handling No-Argument Constructors

In Java, the `new` operator creates an object when the type is known at compile time. When the type is only determined at **runtime** (reading class names from configuration, plugin discovery, data converters, test frameworks, dependency injection), Reflection can find a constructor and invoke it using `java.lang.reflect.Constructor<T>.newInstance(...)`.

The core point: **having a `Class<T>` object does not guarantee that the class has a no-argument constructor**, and finding a constructor does not mean you are allowed to invoke it. You need to accurately distinguish the steps of finding the constructor, checking access permissions, preparing arguments, executing, and handling exceptions thrown inside the constructor.

After this lesson, you will be able to:

- Distinguish `Class.getConstructor(...)` from `Class.getDeclaredConstructor(...)` and choose the right one when a no-argument constructor is needed.
- Create objects using `Constructor.newInstance()` with a public constructor or a parameterized constructor; understand why constructor lookup can fail.
- Understand how a **compiler-provided default constructor** differs from an explicitly declared no-argument constructor.
- Correctly handle `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, `InvocationTargetException`, argument errors, and module restrictions.
- Recognize cases involving interfaces, abstract classes, enums, records, inner classes, and private constructors; decide when to use a factory instead of Reflection.

## 1. From `Class<T>` to a New Instance

Standard Reflection workflow:

```java
Class<Widget> type = Widget.class;                   // 1. Type descriptor object
Constructor<Widget> ctor = type.getConstructor();    // 2. Find public no-argument constructor
Widget widget = ctor.newInstance();                  // 3. Execute constructor to create instance
```

This is an **illustrative snippet**: it requires a `Widget` class with a public no-arg constructor and handling of checked exceptions to run standalone. The arguments passed to `getConstructor(...)` are a list of `Class<?>` representing **declared parameter types**; calling it with no arguments means looking up the signature `()`, not getting the first constructor in the class.

When `newInstance()` succeeds, the JVM allocates the object and runs the normal initialization process: class initialization if needed, superclass initialization, instance initializers, and the constructor body according to Java rules. Invariants are enforced just as when calling `new Widget()`. Reflection is not a mechanism to bypass a constructor; if the constructor throws an exception, object creation fails.

`Class<T>` is the type descriptor; `Constructor<T>` describes a specific constructor; `newInstance(Object... initargs)` **invokes** that constructor. `Constructor<T>` preserves the result type `T` to reduce casts and type assignment errors in code:

```java
Class<Widget> type = Widget.class;
Constructor<Widget> ctor = type.getConstructor();
Widget value = ctor.newInstance();
```

If you only have `Class<?>`, the resulting value is usually used as `Object` or constrained through an explicit type contract. Avoid blind casting from a user-supplied class name.

## 2. Two Constructor Lookup APIs: Public and Declared

| API | Constructors Found | When Not Found | Practical Meaning |
| --- | --- | --- | --- |
| `type.getConstructor()` | Public constructor with exactly **0 parameters** | `NoSuchMethodException` | Want to call the public instantiation API |
| `type.getConstructor(String.class, int.class)` | Public constructor matching `(String, int)` | `NoSuchMethodException` | Want to call a specific public overload |
| `type.getDeclaredConstructor()` | 0-parameter constructor **declared in the class**, regardless of public/protected/package-private/private | `NoSuchMethodException` | Need to inspect or use a non-public constructor |
| `type.getDeclaredConstructor(int.class)` | Declared constructor with exactly one `int` parameter | `NoSuchMethodException` | Use exact signature |
| `type.getConstructors()` | Public constructors of the class | Returns an array, possibly empty | Inspect before choosing |
| `type.getDeclaredConstructors()` | All declared constructors, including non-public ones | Returns an array, possibly empty | Inspect options and modifiers |

A constructor **is not inherited** like an instance method. Therefore, `Child.class.getConstructor()` does not return a constructor declared in `Parent`; it can only return a constructor of `Child` itself. Even if the source code does not write a constructor, the compiler may have generated a default constructor for `Child`, so you still need to check the specific case.

The methods returning an array of constructors **do not guarantee order**; you should not use `getDeclaredConstructors()[0]` to guess the no-arg or "default" constructor. Specify the parameter types explicitly and request the exact signature.

### 2.1. A Found Constructor May Still Not Be Invocable

`getDeclaredConstructor()` can return a private constructor. That method only **discovers metadata**; invocation permission is still checked at `ctor.newInstance()`. In cases where access is restricted, `IllegalAccessException` may be thrown. `setAccessible(true)` or `trySetAccessible()` can allow deep access under certain conditions, but the Java Platform Module System may prevent this. Do not treat `getDeclaredConstructor()` as a tool that automatically bypasses all restrictions.

Read modifiers using `ctor.getModifiers()` together with `Modifier.isPublic(...)` if you need to check policy. However, a public constructor of a non-public class may still be inaccessible to a caller in another package/module; you must consider both the enclosing class's visibility and module relationships.

## 3. No-Argument Constructor and Default Constructor Are Different Concepts

A **no-arg constructor** (no-argument constructor) is a constructor with signature `()`, whether written explicitly or generated by the compiler. A **default constructor** in the JLS is the no-argument constructor provided by the compiler for a normal class when **there are no constructor declarations at all**.

```java
class Automatic {
    // No constructor declared: compiler provides Automatic().
}

class Explicit {
    Explicit() {
        System.out.println("created");
    }
}

class WithParameter {
    WithParameter(String name) {
    }
    // No auto-generated default constructor anymore.
}
```

- `Automatic.class.getDeclaredConstructor()` finds the compiler-generated constructor, with access level matching the class `Automatic` (package-private in the example).
- `Explicit.class.getDeclaredConstructor()` finds the explicitly declared constructor.
- `WithParameter.class.getDeclaredConstructor()` throws `NoSuchMethodException`: **as soon as any constructor is declared**, the compiler does not add a default no-arg constructor.
- None of the three classes above have a public constructor, so `getConstructor()` does not find them (`Automatic`'s constructor is not public). Do not confuse "has a no-arg" with "has a public no-arg".

If a class `public class PublicModel { }` declares no constructors, the compiler provides a corresponding public default constructor; `PublicModel.class.getConstructor()` will find it. A class that has a parameterized constructor and wants to retain no-argument instantiation must declare it explicitly:

```java
class Account {
    private final String owner;

    Account() {
        this("guest");
    }

    Account(String owner) {
        this.owner = owner;
    }
}
```

This is an explicit constructor overload; `Account()` delegates to `Account(String)` to preserve invariants. It has package-private access; `Account.class.getDeclaredConstructor()` finds it, whereas `Account.class.getConstructor()` does not. To use it as a public extension point, design the access level and class contract accordingly.

Do not assume a no-argument constructor will set every field to a business-valid state. A no-argument constructor may set necessary default values; whether an object can be created must be determined by the class contract, not by the preference of a Reflection framework.

## 4. Complete Java 17+ Program: Public Constructors, Overloads, and Exceptions

Create a file named **`ConstructorNewInstanceDemo.java`** with the following content. The nested classes are declared `public static` to expose their constructors and avoid needing an instance of the enclosing class.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorNewInstanceDemo {
    public static class PublicBox {
        private final String value;

        public PublicBox() {
            this("empty");
        }

        public PublicBox(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return "PublicBox[" + value + "]";
        }
    }

    public static class NeedsValue {
        private final int value;

        public NeedsValue(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return "NeedsValue[" + value + "]";
        }
    }

    public abstract static class AbstractJob {
        public AbstractJob() {}
    }

    public static class Exploding {
        public Exploding() {
            throw new IllegalStateException("invalid state");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<PublicBox> noArg =
                PublicBox.class.getConstructor();
        System.out.println(noArg.newInstance());

        Constructor<PublicBox> byName =
                PublicBox.class.getConstructor(String.class);
        System.out.println(byName.newInstance("ready"));

        try {
            NeedsValue.class.getConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("NeedsValue: missing no-arg");
        }

        Constructor<NeedsValue> byNumber =
                NeedsValue.class.getConstructor(int.class);
        System.out.println(byNumber.newInstance(7));

        try {
            AbstractJob.class.getConstructor().newInstance();
        } catch (InstantiationException e) {
            System.out.println("AbstractJob: abstract");
        }

        try {
            Exploding.class.getConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println(
                    "Exploding: " + cause.getClass().getSimpleName()
                            + ": " + cause.getMessage());
        }
    }
}
```

Compile/run with JDK 17 or newer:

```bash
javac --release 17 ConstructorNewInstanceDemo.java
java ConstructorNewInstanceDemo
```

Exact stdout:

```text
PublicBox[empty]
PublicBox[ready]
NeedsValue: missing no-arg
NeedsValue[7]
AbstractJob: abstract
Exploding: IllegalStateException: invalid state
```

Explanation:

1. `PublicBox` has a **public no-arg constructor**, calling `this("empty")`; result is `PublicBox[empty]`.
2. `getConstructor(String.class)` selects the overload taking `String`, creating `PublicBox[ready]`.
3. `NeedsValue` only declares an `(int)` constructor and does not get an auto-generated no-arg constructor from the compiler: **looking up** `()` fails with `NoSuchMethodException`. To create a valid object, the code uses the `(int)` signature and provides the value `7`.
4. `AbstractJob` has a public `()` constructor in metadata, yet it is still an abstract class: **being found does not mean being instantiable**, so `newInstance` throws `InstantiationException`.
5. `Exploding` has a valid constructor, but its body throws `IllegalStateException`; Reflection wraps the original exception in `InvocationTargetException`. Retrieve the cause with `getCause()`, rather than treating it as a missing-constructor error.

The program intentionally catches only the specific errors **being demonstrated**; `main` declares `throws ReflectiveOperationException` for other reflective errors. In real applications, handle them at the framework/API boundary so that stack traces and causes are not lost.

## 5. Creating Objects with Non-Public Constructors

If a framework has appropriate permissions and must invoke a constructor declared `private`, the process consists of: looking it up with `getDeclaredConstructor()`, checking accessibility, requesting access via `trySetAccessible()` when the design allows, and only then calling `newInstance()`.

This example can run standalone on JDK 17 **on the regular classpath (unnamed module)**. Create **`AccessDemo.java`**:

```java
import java.lang.reflect.Constructor;

class Secret {
    private Secret() {}

    String message() {
        return "created";
    }
}

public class AccessDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        try {
            Secret.class.getConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("public no-arg: absent");
        }

        Constructor<Secret> ctor =
                Secret.class.getDeclaredConstructor();
        System.out.println("accessible before: "
                + ctor.canAccess(null));

        try {
            ctor.newInstance();
        } catch (IllegalAccessException e) {
            System.out.println("without override: denied");
        }

        boolean enabled = ctor.trySetAccessible();
        System.out.println("override allowed: " + enabled);
        if (enabled) {
            System.out.println(ctor.newInstance().message());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 AccessDemo.java
java AccessDemo
```

Stdout in the environment described above:

```text
public no-arg: absent
accessible before: false
without override: denied
override allowed: true
created
```

`Secret` is a **separate top-level class**, not a nested class in the same nest as `AccessDemo`. Therefore, `AccessDemo` does not have permission to invoke the private constructor without overriding access. This is important: since Java 11, two **nestmate** classes (for example, an outer class and its nested class) can access each other's private members; writing an example with a private nested class and claiming Reflection will definitely fail would be misleading.

`canAccess(null)` queries current accessibility for the constructor (a constructor does not need a receiver object). `trySetAccessible()` returns `true` if access-check suppression is successfully enabled, or `false` if access cannot be opened under module rules; it can still encounter `SecurityException` under relevant security mechanisms. `setAccessible(true)` throws `InaccessibleObjectException` when the module does not allow opening access in the requested way.

**Module boundaries:** If the class resides in another named module, `exports` normally only allows access to valid public APIs; deep access to private/package-private members may require `opens` on the package for the module performing Reflection. Example module declaration (illustrative, only applicable when you control the module containing the domain class):

```java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
```

You should not blindly add `--add-opens` or open entire packages just to "make code run" in production. Prefer designing public factories, explicit public constructors, or supported extension APIs. When permission is not granted, report a contextual error instead of trying to bypass the Java module system.

## 6. Exception Table: Which Step Does the Error Occur At?

| Exception / Error | Common Step | Typical Cause | How to Handle |
| --- | --- | --- | --- |
| `NoSuchMethodException` | `getConstructor` / `getDeclaredConstructor` | No constructor with the exact signature; e.g., missing `()`, or mismatching `int.class` vs `Integer.class` | Check signature; choose a valid overload or factory; do not auto-generate no-arg |
| `IllegalAccessException` | `ctor.newInstance` | Constructor or declaring class is inaccessible to the caller | Respect visibility; use public API, or open access if permitted |
| `InstantiationException` | `ctor.newInstance` | E.g., declaring class is an abstract class | Do not try to instantiate abstract classes; use a concrete implementation |
| `InvocationTargetException` | `ctor.newInstance` | Code inside the constructor threw an exception/error | Extract `getCause()`, preserve root cause, and propagate at the proper responsibility layer |
| `IllegalArgumentException` | `ctor.newInstance` | Wrong argument count/types, invalid `null` for primitive, or attempting to instantiate an enum via Reflection | Select exact signature, validate argument values and shapes |
| `ExceptionInInitializerError` | Class initialization when invoking constructor | Static initialization of the declaring class failed | Inspect static initializer and root cause; do not confuse with a constructor error |
| `InaccessibleObjectException` | `setAccessible(true)` | Cannot suppress access check because the module has not opened the package | Use public API or configure module properly |
| `SecurityException` | Lookup / changing accessibility in an environment with security checks | Security policy blocks the corresponding permission | Do not attempt to bypass permissions; return an appropriate error |

Not every exception is a subclass of `ReflectiveOperationException`: `IllegalArgumentException`, `InaccessibleObjectException`, `ExceptionInInitializerError`, and `SecurityException` must be considered separately depending on the API and context. Meanwhile, `NoSuchMethodException`, `InstantiationException`, `IllegalAccessException`, and `InvocationTargetException` are all checked reflection exceptions in the `ReflectiveOperationException` hierarchy.

**How to properly read `InvocationTargetException`:** This is a wrapper indicating "the invoked method/constructor threw an error". `e.getCause()` is the actual exception/error that occurred inside. The wrapper's `getMessage()` may not describe the cause. Never just log `InvocationTargetException` and discard `getCause()`.

Example handling snippet used inside a method declared `throws ReflectiveOperationException`:

```java
try {
    return ctor.newInstance();
} catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    if (cause instanceof RuntimeException re) {
        throw re;
    }
    if (cause instanceof Error error) {
        throw error;
    }
    throw new IllegalStateException("Constructor failed", cause);
}
```

This is only **a handling branch inside a method** where `ctor` already exists, not a standalone program. An application may want to wrap all errors into a domain/framework-specific exception; if so, still preserve `cause` so the original evidence is not lost.

## 7. No No-Arg Constructor: How Should You Handle It?

For a class requiring mandatory data to protect invariants, the absence of a no-arg constructor can be completely intentional design:

```java
class ConnectionOptions {
    private final String host;
    private final int port;

    public ConnectionOptions(String host, int port) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host is required");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
        this.host = host;
        this.port = port;
    }
}
```

`ConnectionOptions.class.getConstructor()` will throw `NoSuchMethodException`. Do not "fix" this by "creating an empty object" if that object type has no valid empty state. The proper way to create it is:

```java
Constructor<ConnectionOptions> ctor =
        ConnectionOptions.class.getConstructor(String.class, int.class);
ConnectionOptions options =
        ctor.newInstance("localhost", 8080);
```

This is an illustrative snippet inside a method that handles checked exceptions; `ConnectionOptions` and `ctor` must be in the same package or an environment with appropriate access. Because `ConnectionOptions` in the example is not public, code in another package may not be able to invoke the constructor even though the member constructor is declared `public`. If you want a public API across packages, declare the class itself `public` in an appropriate file.

Decision process when encountering `NoSuchMethodException`:

1. Confirm the actual signatures using `getDeclaredConstructors()` during diagnostics; do not rely on array order.
2. If an appropriate parameterized constructor exists, select it with exact `Class<?>` arguments and prepare valid argument values.
3. If the class provides a static factory (`of(...)`, `create(...)`), builder, or factory interface, prefer that contract when designed for the use case.
4. If a framework mandates a public no-arg constructor to fulfill a contract, require the plugin/model type to provide an appropriate constructor or register a custom factory. Do not silently add a no-arg constructor that breaks invariants.
5. If there is no valid instantiation path, return a configuration error containing the class name, required signature, and remediation; do not create objects using tricks that skip initialization.

Even if designing a fallback, **never automatically pick the constructor with the "fewest parameters"** and arbitrarily pass `null`/`0`. That breaks the domain contract and can cause failures far from where the object was created.

## 8. Passing Correctly Typed Arguments to `newInstance(Object...)`

Constructor lookup is **exact signature matching**; only when invoking the constructor are allowed conversions applied. For example:

```java
record Purchase(int quantity, String item) {}

Constructor<Purchase> ctor =
        Purchase.class.getDeclaredConstructor(int.class, String.class);
Purchase purchase =
        ctor.newInstance(Integer.valueOf(3), "book");
```

This snippet requires importing `java.lang.reflect.Constructor` and handling exceptions. `getDeclaredConstructor(int.class, String.class)` succeeds because the declaration takes primitive `int`; when calling `newInstance`, `Integer.valueOf(3)` is **unboxed** to `int` according to Reflection rules. However, `getDeclaredConstructor(Integer.class, String.class)` will fail because there is no constructor with that declared signature.

Important notes:

- **Parameter order and count:** `(String, int)` differs from `(int, String)`. If `newInstance` receives too few or too many arguments, it may throw `IllegalArgumentException`.
- **Primitive conversion:** `newInstance` can unbox wrappers and apply valid primitive widening; it does not perform arbitrary narrowing. Passing `null` to a primitive parameter is invalid.
- **Reference conversion:** objects must be compatible with the declared parameter type. `getConstructor` does not automatically find the "closest overload" when you supply a different parameter type.
- **Generic erasure:** if a constructor is declared to take `List<String>`, use `List.class` for the raw parameter type when looking it up via Reflection; there is no `List<String>.class` literal.
- **Varargs of the Reflection API itself:** `Constructor.newInstance(Object... initargs)` takes a list of `Object`; distinguish this from an array that is actually **a single parameter** of the target constructor.

The last case is very easy to get wrong:

```java
class Names {
    public Names(String... items) {
        System.out.println(items.length);
    }
}
```

The Reflection signature is `(String[])`, not `(String, String)`. The correct way to invoke it (inside a method handling exceptions):

```java
Constructor<Names> ctor = Names.class.getDeclaredConstructor(String[].class);
ctor.newInstance((Object) new String[] {"A", "B"}); // stdout: 2
```

Casting to `Object` here makes the `String[]` array **one argument** in the `Object...` varargs of the Reflection API. If you omit the cast and write `ctor.newInstance(new String[] {"A","B"})`, the compiler can apply varargs in a way that treats the array as multiple arguments, causing the call not to match the actual signature. Therefore, in general code that invokes constructors with array parameters, wrap the argument explicitly.

**No-arg:** calling `ctor.newInstance()` is clearest. Do not try to "fix" no-arg with an arbitrary `null`: `ctor.newInstance((Object) null)` means passing **one null argument**, not zero arguments.

## 9. Special Class Kinds: No-Arg Constructors May Not Exist or Be Usable

| `Class<?>` Kind | What to Watch Out For | How to Handle |
| --- | --- | --- |
| Interface | Has no constructors, cannot be directly instantiated with `new` | Find a concrete implementation or an intentional factory/proxy |
| Abstract class | May have constructors for subclasses to call, but cannot be instantiated directly | Choose a concrete subclass |
| Primitive, `void`, array | Has no class-style constructors to look up with this API | Use `java.lang.reflect.Array.newInstance` for arrays when needed; primitive/void have no instances this way |
| Enum | Does not allow creating additional enum constants via `Constructor.newInstance` | Use existing constants, `getEnumConstants()`, `Enum.valueOf(...)` |
| Record | By default has a canonical constructor matching record components; does not automatically have a no-arg | Use the canonical constructor or declare a valid no-arg constructor with `this(...)` |
| Non-static inner class | Runtime constructor normally has an enclosing instance parameter first, even if source writes `()` | Provide an instance of the outer class and look up the exact signature |
| Static nested class | Has no implicit outer instance parameter | Treat like a normal class |
| Private/package-private class | Constructor may be found, but cannot be invoked from other callers | Follow accessibility/module rules or expose a factory |

### 9.1. Records and Data-Required Initialization

```java
record Endpoint(String host, int port) {}
```

`Endpoint.class.getDeclaredConstructor()` throws `NoSuchMethodException` because the canonical constructor has two parameters. Valid invocation:

```java
Constructor<Endpoint> ctor =
        Endpoint.class.getDeclaredConstructor(String.class, int.class);
Endpoint endpoint = ctor.newInstance("localhost", 8080);
```

If business logic has a genuinely valid default state, a record can declare an additional no-argument constructor and **must delegate to another constructor using `this(...)`**:

```java
record DefaultEndpoint(String host, int port) {
    DefaultEndpoint() {
        this("localhost", 8080);
    }
}
```

`DefaultEndpoint.class.getDeclaredConstructor()` can now be found; however, this is an intentional design decision, not a constructor auto-generated by the compiler for every record.

### 9.2. Non-Static Inner Classes and the Hidden Outer Parameter

```java
class Outer {
    class Inner {
        Inner() {}
    }
}
```

In source code, `Inner()` looks parameterless, but a non-static inner class is bound to an enclosing `Outer` instance. When looked up via core Reflection, the enclosing instance appears as the first parameter. Illustrative example in the same package, with `ReflectiveOperationException` handled:

```java
Outer outer = new Outer();
Constructor<Outer.Inner> ctor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class);
Outer.Inner inner = ctor.newInstance(outer);
```

`Outer.Inner.class.getDeclaredConstructor()` does not find an actual `()` signature. If a Reflection tool encounters a nested class, check `getEnclosingClass()`, `Modifier.isStatic(...)`, and the constructor signature instead of assuming the author forgot a no-arg constructor.

## 10. Building a Clear Utility for Creating Objects with Public No-Arg

The following snippet is a **reusable method**, placed inside a Java 17+ utility class importing `java.lang.reflect.Constructor`, `java.lang.reflect.InvocationTargetException`, and `java.lang.reflect.Modifier`. This is not a standalone file; the goal is to make error paths explicit:

```java
static <T> T createWithPublicNoArg(Class<T> type) {
    if (type == null) {
        throw new IllegalArgumentException("type is null");
    }
    if (type.isInterface()
            || java.lang.reflect.Modifier.isAbstract(type.getModifiers())
            || type.isPrimitive()
            || type == void.class
            || type.isArray()
            || type.isEnum()) {
        throw new IllegalArgumentException(
                "Cannot instantiate: " + type.getTypeName());
    }

    try {
        Constructor<T> ctor = type.getConstructor();
        return ctor.newInstance();
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "Missing public no-arg constructor: "
                        + type.getTypeName(), e);
    } catch (InvocationTargetException e) {
        Throwable cause = e.getCause();
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        if (cause instanceof Error error) {
            throw error;
        }
        throw new IllegalStateException(
                "Constructor failed: " + type.getTypeName(), cause);
    } catch (InstantiationException | IllegalAccessException e) {
        throw new IllegalStateException(
                "Constructor is not invocable: "
                        + type.getTypeName(), e);
    }
}
```

The intent of the utility is **public no-arg only**. It does not open private constructors and does not infer how to instantiate types lacking a no-arg constructor. Pre-checks help produce clear error messages; checked exceptions must still be caught because actual state and accessibility are determined at invocation time.

The `Modifier.isAbstract` check is necessary alongside `isInterface()` to identify abstract classes. Public classes with a public constructor where the class itself is inaccessible to the caller can still cause `IllegalAccessException`. Static initializer errors or runtime errors independent of checked exceptions must be handled at a higher boundary if the API requires it.

In applications with many plugin types, a better option is registering a `Supplier<? extends Service>`, an appropriate factory, or dependency injection. That way object creation can take parameters and dependencies, avoiding forcing every implementation to provide a no-arg constructor.

## 11. Why Should You Stop Using `Class.newInstance()`?

The old API:

```java
Widget instance = Widget.class.newInstance();
```

has been **deprecated since Java 9**. It only follows no-argument instantiation and specifically can propagate exceptions thrown by the constructor directly, including checked exceptions, bypassing compile-time exception checking.

Recommended way when Reflection is needed:

```java
Constructor<Widget> ctor =
        Widget.class.getDeclaredConstructor();
Widget instance = ctor.newInstance();
```

Meaningful differences:

- If there is no `()` constructor, `getDeclaredConstructor()` clearly throws `NoSuchMethodException`.
- If the constructor runs and throws an exception, `Constructor.newInstance()` wraps it in `InvocationTargetException` so the caller handles it through a unified mechanism.
- Finding a non-public constructor **does not** bypass access checks. If the contract only allows public constructors, use `getConstructor()` instead.

Do not convert `type.newInstance()` to `type.getDeclaredConstructor().newInstance()` via simple find-and-replace and swallow all exceptions. You must decide on explicit public access, module permissions, non-instantiable class cases, and how to preserve the cause.

## 12. Common Real-World Mistakes

1. **"Having a `Class` guarantees having `()`."** False: a class with a parameterized constructor will not automatically have a default no-arg constructor. Use `getConstructor()`/`getDeclaredConstructor()` and handle `NoSuchMethodException`.
2. **"A public constructor means a public class."** False: a public member can belong to a declaring class inaccessible to the caller; Reflection still checks the declaring class's accessibility.
3. **"No public constructor found means the class has no constructor."** False: try `getDeclaredConstructor()` when the task is permitted to inspect private/package-private constructors.
4. **"`getDeclaredConstructor()` guarantees a private constructor can be invoked."** False: metadata lookup is separate from invocation permission; `trySetAccessible` may fail, and the module system may block deep access.
5. **"`NoSuchMethodException` means the constructor ran and failed."** False: it occurs at the **signature lookup step**. `InvocationTargetException` is what indicates the invoked code threw an error.
6. **"`InvocationTargetException` is the root cause."** False: use `getCause()`, and do not turn a domain error into a hard-to-diagnose "Reflection failed" message.
7. **"Just `catch (Exception ignored)` and return null."** False: this loses the cause and leads to a `NullPointerException` far from the root error. Return a typed error with cause or handle at a higher layer.
8. **"Java automatically finds a compatible constructor overload when calling `getConstructor(Integer.class)`."** False: signature lookup is exact; unboxing/widening is considered at invocation time.
9. **"Calling `newInstance(null)` passes no arguments."** This is an ambiguous varargs expression; for zero arguments, use `newInstance()`. If you intend to pass a single `null` reference, write `newInstance((Object) null)` explicitly.
10. **"Use `Unsafe.allocateInstance` instead of a constructor to bypass no-arg errors."** That can bypass constructors and invariants and is not a safe fix for normal domain classes or frameworks.
11. **"Enums, records, and inner classes all have no-arg constructors like POJOs."** Enums cannot have additional constants created via `Constructor.newInstance`; records usually need their canonical constructor; non-static inner classes need an enclosing instance.
12. **"No-argument constructors are always harmless."** Constructors and class initialization can have side effects, throw errors, allocate resources, or cause unintended effects; do not run classes from untrusted input just because Reflection allows it.

## 13. Testing Tips When Developing Frameworks Using Reflection

You should have separate test cases for: successful public no-arg; class with parameterized constructor lacking no-arg; private no-arg with opened/unopened module; abstract class; constructor throwing checked or unchecked exception; constructor with primitive parameter; non-static inner class; record and enum. These cases distinguish **lookup, access, instantiation, and target logic errors**, which a single happy-path test usually misses.

At the layer that receives class names from configuration, restrict the set of instantiable types; do not allow arbitrary input to trigger initialization/constructors of any class. You can require the type to implement a shared interface:

```java
if (!Service.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException("Not a Service type");
}
Class<? extends Service> implementation =
        candidate.asSubclass(Service.class);
Service service = createWithPublicNoArg(implementation);
```

This snippet illustrates the case when you already have a `Service` interface, a `candidate` variable of type `Class<?>`, and the utility method from section 10. `asSubclass` provides a runtime check and type constraint; it does not certify that the class is trusted or that its constructor has no side effects. When designing a plugin system, add a registration/allowlist policy for specific implementations.

## 14. Self-Check Questions

**1.** `class A { A(int x) {} }`. Why does `A.class.getDeclaredConstructor()` fail? What constructor should be added if you want to create `A` without arguments?

**Answer:** because the class already declares an `(int)` constructor, the compiler does not generate a default `()`. Add `A() { this(0); }` **if `0` is a valid state**, or supply an appropriate argument to the existing constructor.

**2.** Why can `getDeclaredConstructor()` find a private constructor, yet `newInstance()` can still throw `IllegalAccessException`?

**Answer:** metadata lookup and access checking at execution are two different steps. The caller may not be permitted to invoke the private constructor; overriding access is subject to language access and module constraints.

**3.** How does `NeedsValue.class.getConstructor(int.class)` differ from `NeedsValue.class.getConstructor(Integer.class)` given `public NeedsValue(int value)`?

**Answer:** the first signature matches, while the second throws `NoSuchMethodException`. Once the `int` constructor is found, `newInstance(Integer.valueOf(7))` can unbox at invocation time.

**4.** A constructor body executes `throw new IllegalStateException("broken")`. What exception does the caller observe from `ctor.newInstance()`?

**Answer:** `InvocationTargetException`; `e.getCause()` is `IllegalStateException("broken")`.

**5.** Why can an abstract class with a public no-arg constructor still not be instantiated via Reflection?

**Answer:** the constructor exists for subclasses, but an abstract class cannot have a direct instance; `Constructor.newInstance()` throws `InstantiationException`.

**6.** Given `record User(String name) {}`, does calling `User.class.getDeclaredConstructor()` work? What is the valid way to instantiate it?

**Answer:** no, it does not automatically have a no-arg constructor; look up the canonical constructor with `getDeclaredConstructor(String.class)` and pass `name`, or design an explicit no-arg constructor delegating to `this(...)` if there is a valid default value.

**7.** In Reflection, what signature is normally used to look up the source constructor `Inner()` of a non-static `Outer.Inner`?

**Answer:** `Outer.Inner.class.getDeclaredConstructor(Outer.class)`, because an enclosing `Outer` instance must be passed as the first argument when instantiating.

**8.** A plugin system requires a no-arg constructor, but one plugin needs a mandatory dependency. Should you add a no-arg constructor to every class or change the instantiation mechanism?

**Answer:** if a no-arg constructor cannot guarantee invariants, register a factory/`Supplier` or use DI to provide dependencies. Only require a public no-arg constructor when it is an explicit and valid contract for all implementations.

## Authoritative Reference Documentation

- Java SE 21 API `Constructor<T>`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html — how to call `newInstance`, parameter conversions, exceptions, and access control.
- Java SE 21 API `Class<T>`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html — `getConstructor`, `getDeclaredConstructor`, cases with no constructor, deprecated `Class.newInstance()`.
- Java SE 21 API `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html — `canAccess`, `trySetAccessible`, `setAccessible` in the Java module system.
- Java Language Specification 21, §8.8 Constructors and §8.10 Record Classes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html — default constructors, inner class parameters, record canonical constructors.