# Private Constructors and Access Conditions in Java Reflection

## 1. What Problem Does a Private Constructor Solve?

A constructor is a special member used to initialize an instance. Declaring a constructor `private` **restricts where the constructor can be called according to the Java language**, commonly used to control object creation, force callers through a factory method, or prevent instantiating a utility class.

~~~java
final class SecretBox {
    private final String value;

    private SecretBox(String value) {
        this.value = value;
    }

    public static SecretBox of(String value) {
        return new SecretBox(value);
    }
}
~~~

This is a short illustrative snippet: ordinary code outside the permitted scope cannot write `new SecretBox("abc")` because the constructor is private; instead it calls `SecretBox.of("abc")`. However, Java Reflection **can look up the metadata of a private constructor**, and under certain conditions can request bypassing access checks when invoking it. That capability depends on the caller, package/module scope, and deep reflection permissions.

Therefore, three questions must be clearly distinguished:

1. **Is the constructor declared in the class?** Check via `getDeclaredConstructor(...)` or `getDeclaredConstructors()`.
2. **Does the caller have permission to invoke the constructor found?** Permission is checked when using `Constructor.newInstance(...)`; `Constructor.canAccess(null)` probes current permission.
3. **Is enabling the access-check override allowed?** `trySetAccessible()` or `setAccessible(true)` only works when access boundaries allow it.

**Finding a constructor does not mean being able to invoke the constructor.** This is the central point when working with private constructors via Reflection.

## 2. `getConstructor` vs. `getDeclaredConstructor`

| API of `Class<T>` | Lookup scope | Retrieves private constructors? |
| --- | --- | --- |
| `getConstructor(Class<?>... parameterTypes)` | Only public constructors declared on the class itself | No |
| `getConstructors()` | Array of public constructors of the class itself | No |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | Constructors declared on the class itself, regardless of modifier | Yes |
| `getDeclaredConstructors()` | All constructors declared on the class itself: public, protected, package-private, and private | Yes |

Unlike many public methods/fields, **constructors are not inherited**. For example, `Child extends Parent` does not make constructor `Parent(int)` a constructor `Child(int)`. Both API groups above look up constructors of **the class under examination**, not inherited constructors.

The two single-constructor lookup APIs require the **exact list of parameter types**, in exact order, as `Class` objects:

~~~java
Constructor<SecretBox> ctor =
        SecretBox.class.getDeclaredConstructor(String.class);
~~~

If the constructor actually takes `String`, pass `String.class`; if it takes primitive `int`, pass `int.class`, do not substitute `Integer.class`. Lookup does not perform overload resolution like `new` syntax and does not automatically convert types for you. A wrong signature throws `NoSuchMethodException`, while `getDeclaredConstructor` does not require the constructor to be public.

**Modifiers and declaring location:** You can check `Modifier.isPrivate(ctor.getModifiers())`, `ctor.getDeclaringClass()`, `ctor.getParameterTypes()`, and `ctor.isVarArgs()` to inspect metadata. Reading this metadata does not by itself grant permission to run the constructor.

## 3. Java 17+ Example: Lookup, Blocked Call, Opening Access, Instantiation

Create the file **`PrivateCtorDemo.java`**, containing **two separate top-level classes**. Placing `PrivateCtorDemo` and `SecretBox` in the same file/package keeps the example simple, yet they **are not nested classes/nestmates**, so `SecretBox`'s private constructor is not naturally accessible from `PrivateCtorDemo`.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;

public class PrivateCtorDemo {
    public static void main(String[] args) throws Exception {
        Class<SecretBox> type = SecretBox.class;

        try {
            type.getConstructor(String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("public lookup: " + e.getClass().getSimpleName());
        }

        Constructor<SecretBox> ctor =
                type.getDeclaredConstructor(String.class);

        System.out.println("private: "
                + Modifier.isPrivate(ctor.getModifiers()));
        System.out.println("canAccess before: " + ctor.canAccess(null));

        try {
            ctor.newInstance("alpha");
        } catch (IllegalAccessException e) {
            System.out.println("invoke before: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("opened: " + ctor.trySetAccessible());
        System.out.println("canAccess after: " + ctor.canAccess(null));
        System.out.println("created: " + ctor.newInstance("alpha").code());

        try {
            ctor.newInstance("");
        } catch (InvocationTargetException e) {
            System.out.println("target error: "
                    + e.getCause().getClass().getSimpleName());
        }

        ctor.setAccessible(false);
        System.out.println("canAccess reset: " + ctor.canAccess(null));
    }
}

class SecretBox {
    private final String code;

    private SecretBox(String code) {
        if (code.isBlank()) {
            throw new IllegalArgumentException("empty code");
        }
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Compile with a Java 17-compatible compiler, then run on the classpath:

~~~bash
javac --release 17 PrivateCtorDemo.java
java PrivateCtorDemo
~~~

Expected output of the example when run in an ordinary unnamed module/classpath:

~~~text
public lookup: NoSuchMethodException
private: true
canAccess before: false
invoke before: IllegalAccessException
opened: true
canAccess after: true
created: alpha
target error: IllegalArgumentException
canAccess reset: false
~~~

### Step-by-Step Explanation

**Stage 1 — Searching only for public constructors.** `type.getConstructor(String.class)` throws `NoSuchMethodException` because `SecretBox(String)` is private. This **does not say** the constructor does not exist, rather that it is not in the set of public constructors for that lookup method.

**Stage 2 — Finding the exact declaration.** `type.getDeclaredConstructor(String.class)` returns `Constructor<SecretBox>`. `Modifier.isPrivate(...)` is `true`. `canAccess(null)` is currently `false` because the caller is in a different top-level class and the private constructor has not been opened.

**Stage 3 — Invoking without permission.** `ctor.newInstance("alpha")` performs the access check and throws `IllegalAccessException`. The constructor body has not run, so no object is created from this blocked call.

**Stage 4 — Enabling valid override.** `ctor.trySetAccessible()` returns `true` in the example's classpath environment. Then Java language access checks are bypassed **for the reflection object `ctor`**, `canAccess(null)` becomes `true`, and `ctor.newInstance("alpha")` creates the object; accessing `code()` yields `alpha`.

**Stage 5 — Error from constructor logic.** `ctor.newInstance("")` passed the permission check, but the constructor body itself throws `IllegalArgumentException` on a blank string. Reflection wraps the target's error in `InvocationTargetException`; `getCause()` shows the root cause is `IllegalArgumentException`. This case **differs from** the `IllegalAccessException` in stage 3.

**Stage 6 — Restoring normal access checks.** `ctor.setAccessible(false)` turns off the override on the `Constructor` object; `canAccess(null)` goes back to `false` for this caller.

This is a behavioral analysis exercise, **not advice to always enable private access in production code**. The `opened: true` result is only an outcome under the example's execution conditions, not a guarantee for all named modules or libraries.

## 4. When Can `Constructor.newInstance` Be Invoked Without Override?

The condition for `Constructor.newInstance` depends on **the actual caller context**, not only the modifier:

- A `public` constructor of a type accessible to the caller can be invoked directly or via Reflection without enabling an override.
- A `private` constructor is normally only accessible from code inside the declaring class itself or **nestmates** permitted by the Java language; outside callers like `PrivateCtorDemo` in the example above are blocked.
- A package-private constructor can be called by code in the same package when other conditions are satisfied; `protected` follows rules for package/subclass and access context.
- An inaccessible class itself (for example, a package-private top-level class in another package, or a public class in a package not exported to the calling named module) can block access even if the constructor has a public modifier.

Therefore, `getDeclaredConstructor` only proves that metadata was found. **Do not infer from `getModifiers()` that invocation will always succeed.** The access check also considers the declaring class, caller relationship, module, and override state.

One easily confusing detail in practice: if you place a private constructor in a **nested class** and invoke Reflection from the outer class in the same nest, Java may treat those classes as **nestmates** with language-level private access. Then `canAccess(null)` may already be `true`, and the call will not suffer `IllegalAccessException`. To demonstrate a blocked call clearly, place the caller in a **separate top-level class** as in the program above.

## 5. `canAccess(null)`, `trySetAccessible`, and `setAccessible`

`Constructor<T>` inherits from `AccessibleObject`, so it provides these APIs:

| API | Meaning | Key behavior |
| --- | --- | --- |
| `ctor.canAccess(null)` | Checks permission to use the constructor from the current caller | Returns `boolean`, does not enable access itself |
| `ctor.trySetAccessible()` | Attempts to enable the language access-check override | Returns `true` if enabled, `false` if access boundaries forbid it |
| `ctor.setAccessible(true)` | Requests enabling the override | May throw `InaccessibleObjectException` when it cannot be opened |
| `ctor.setAccessible(false)` | Disables the override | Subsequent calls must obey normal permission checks |

A constructor **has no pre-existing receiver**; therefore use `null` for `canAccess`. Do not confuse this with `Method.canAccess(receiver)` or `Field.canAccess(receiver)` for instance members. `Constructor.newInstance(...)` takes **arguments passed to the constructor**, not a receiver; argument count/types must match the signature.

Pre-invocation check pattern:

~~~java
Constructor<SecretBox> constructor =
        SecretBox.class.getDeclaredConstructor(String.class);
if (!constructor.canAccess(null) && !constructor.trySetAccessible()) {
    throw new IllegalStateException(
            "Not allowed to invoke constructor of SecretBox");
}
SecretBox instance = constructor.newInstance("alpha");
~~~

This is an **illustrative code snippet** reusing the `SecretBox` definition from the example; not a standalone file. It shows the check and handling when the access-opening branch is denied. The snippet does not solve all errors: `newInstance` can still fail if the constructor itself throws an exception, arguments have wrong types, or class initialization fails.

`setAccessible(true)`/`trySetAccessible()` **does not modify the `private` modifier in the class file**, does not turn the constructor public for all code, and does not skip argument type checking or validation logic inside the constructor. The override belongs to the specific reflection object being used.

## 6. JPMS: Why Does the Same Code Work on the Classpath Yet Fail in a Named Module?

When the Java Platform Module System (Java 9+) is used with **named modules**, public API and deep reflection have separate boundaries. A private constructor located in a package of a named module is not necessarily open to another module merely because its metadata can be looked up.

Consider two modules `com.example.domain` (containing the target class) and `com.example.framework` (needing Reflection). The domain module's descriptor might declare:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.internal to com.example.framework;
}
~~~

Meaning:

- `exports com.example.domain.api;` allows eligible modules to access public types/members in the API package per Java rules. **`exports` does not automatically permit deep reflection into private constructors**.
- `opens com.example.domain.internal to com.example.framework;` allows the framework module to use deep reflection in the internal package, provided other conditions match. A package that is `opens` does not thereby become public API that can be arbitrarily imported at compile time.
- If a package is not opened to the calling module and the caller is not in a JPMS-permitted case, `ctor.trySetAccessible()` can return `false`; `ctor.setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException` (unchecked).
- A caller in the **same module** as the declaring class has different capabilities than a cross-module caller. For classes on the classpath belonging to the unnamed module, packages are typically open for deep reflection, so simple examples can enable overrides.

If a program genuinely needs a framework to invoke a private constructor in another module, the module designer can intentionally open the right package, e.g., `opens ... to ...`, or provide a public factory API to avoid depending on private implementation details. During deployment, the JVM option `--add-opens module/package=caller-module` can also grant matching open access, but that configuration must be managed explicitly and should not be used as a "quick fix" for an under-designed API.

**Do not generalize the logic from the example above into "a private constructor can always be invoked with setAccessible(true)".** That is not a JPMS guarantee.

## 7. Common Exceptions Step by Step

| Step | Error/Result | How to understand |
| --- | --- | --- |
| `getConstructor(String.class)` | `NoSuchMethodException` | No **public** constructor with the requested signature; a private constructor may still exist |
| `getDeclaredConstructor(...)` | `NoSuchMethodException` | No constructor directly declared with the exact parameter type list |
| `ctor.newInstance(...)` when access check denies | `IllegalAccessException` | Caller is not allowed to invoke the constructor in its current state |
| `ctor.trySetAccessible()` | `false` | Cannot enable access-check override for the caller, often due to JPMS boundaries |
| `ctor.setAccessible(true)` | `InaccessibleObjectException` | Request to open access exceeds what JPMS permits |
| `ctor.newInstance(...)` wrong argument count/type | `IllegalArgumentException` | Incompatible signature or receiver/arguments per contract |
| `ctor.newInstance(...)` when constructor body throws | `InvocationTargetException` | Inspect `getCause()` to obtain the original error thrown by the target constructor |
| `ctor.newInstance(...)` with abstract class | `InstantiationException` | Type cannot be directly instantiated |
| Class initialization fails during execution | Possibly `ExceptionInInitializerError` | Error occurred when JVM ran static initialization, separate from constructor access |

`IllegalAccessException` and `InvocationTargetException` are two different situations: the first typically means you are not allowed to run the constructor yet; the second indicates the target constructor was invoked and internal logic threw an error. Well-written Reflection code should not catch all `Exception`s and report "no permission".

Constructors of **enums** also have special constraints: Reflection cannot use `Constructor.newInstance` to create new enum constants, even if constructor metadata has been found. Constructors belonging to a **non-static inner class** may also contain a hidden parameter representing the outer class instance; the lookup signature must match what the compiler actually generated. This is why inspecting `getParameterTypes()` rather than guessing the signature matters.

## 8. Private Constructors in Singletons, Utility Classes, and Frameworks

### Utility Classes

A class with only static methods often uses a private constructor to prevent ordinary instantiation:

~~~java
public final class TextUtils {
    private TextUtils() {
        throw new AssertionError("Utility class");
    }

    public static String trim(String value) {
        return value == null ? null : value.trim();
    }
}
~~~

This pattern does not make the class "impossible to instantiate under all circumstances". If code has valid Reflection permission to enter the private constructor, calling `newInstance()` will run the constructor body and throw `AssertionError`, wrapped in `InvocationTargetException`. Therefore, a private constructor should not be viewed as a standalone security boundary.

### Singletons/Factories

A singleton or factory class can rely on a private constructor to control instance count and validation. Deep reflection can bypass the **language access barrier** when a package is open, yet it does not automatically skip validation inside the constructor. If a project needs to guarantee invariants or strict identity, it must design immutability, lifecycle, and management mechanisms appropriately; do not place all correctness guarantees on the `private` modifier.

### Frameworks and Dependency Injection

Some frameworks need to create objects from non-public constructors. They typically:

1. Find a matching constructor via `getDeclaredConstructors()` or `getDeclaredConstructor(...)`.
2. Select a constructor based on annotations/signatures or specific design rules.
3. Check accessibility; if deep reflection is needed, require `opens` for the framework module.
4. Invoke `Constructor.newInstance(...)` with valid arguments and report errors distinguishing access permissions, wrong signatures, or body exceptions.

Do not assume every framework can open private constructors of every library/JDK class; in named modules, package-opening configuration is part of the operational contract.

## 9. Comparing `Constructor.newInstance` with `Class.newInstance`

`Class.newInstance()` is an old API and is **deprecated**. It requires a matching no-arg constructor and handles exceptions from the constructor less clearly than `Constructor.newInstance`.

Modern approach to use when Reflection is needed:

~~~java
Constructor<MyType> ctor = MyType.class.getDeclaredConstructor();
MyType item = ctor.newInstance();
~~~

This is an illustrative snippet, assuming `MyType` exists and has a no-arg constructor; not a standalone program. If that constructor is private and the caller lacks access, `canAccess(null)` and the ability to open access still need evaluation. `Constructor.newInstance` wraps exceptions from the constructor body in `InvocationTargetException`, helping distinguish target logic errors from access errors.

In normal application code, if a public factory or `new` syntax meets the goal, direct invocation remains easier to read and control. Use Reflection only when there is a clear technical reason such as DI, serialization, testing, or tooling.

## 10. Practical Checklist and Self-Check

1. **Know the exact target class:** constructors are not inherited; use the exact `Class<?>` of the class you want to create.
2. **Know the signature:** use `getDeclaredConstructor(int.class, String.class)` if the constructor actually takes `int, String`; `Integer.class` is not equivalent to `int.class` during lookup.
3. **Distinguish public lookup and declared lookup:** `getConstructor` does not see private; `getDeclaredConstructor` can see it but does not grant access.
4. **Check permission from the actual caller:** `ctor.canAccess(null)` and whether `trySetAccessible()` succeeds; do not guess the outcome solely from modifiers.
5. **Respect packages and JPMS:** if non-public access across modules is needed, check targeted `opens` and use permitted APIs.
6. **Handle errors separately:** `NoSuchMethodException` is lookup; `IllegalAccessException` is access; `InvocationTargetException.getCause()` is an error from the constructor body; `IllegalArgumentException` usually relates to signature/arguments.
7. **Avoid treating private as absolute security:** legitimate Reflection can bypass language access barriers; object invariants need protection within the design itself.

**Question 1.** `getDeclaredConstructor(String.class)` returns a `Constructor` for a private constructor. Can `newInstance("x")` be called immediately? **Not necessarily**: caller permissions and access-check override status must be considered.

**Question 2.** Why does `getConstructor(String.class)` throw `NoSuchMethodException` while `getDeclaredConstructor(String.class)` succeeds? **Because the first searches only public constructors, while the second searches directly declared constructors at any access level.**

**Question 3.** `trySetAccessible()` returns `false` when a framework in another module accesses a private constructor. How to handle it? **Use a permitted API or explicitly open the package via `opens` per module design; do not proceed as if the override were enabled.**

**Question 4.** A constructor itself throws `IllegalArgumentException`. When `Constructor.newInstance` runs, what exception type does the caller observe? **`InvocationTargetException`**, and the original exception is retrieved via `getCause()`.

**Question 5.** Do you need `canAccess(someObject)` before invoking a constructor? **No.** A constructor has no receiver yet; call `canAccess(null)`.

When working with private constructors via Java Reflection, follow the exact sequence **find constructor → determine permissions and module boundaries → consider opening access → invoke with valid arguments → handle exceptions from the constructor**. This separation keeps Reflection code semantically accurate, transparent about permissions, and easy to maintain.
