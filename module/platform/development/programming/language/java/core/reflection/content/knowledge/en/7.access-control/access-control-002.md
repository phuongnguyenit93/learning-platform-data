# Java access checks on `get`, `set`, `invoke`, or `newInstance`

## 1. Finding a member differs from having permission to use it

Reflection has two separate stages:

1. **Metadata lookup**: `Class.getField`, `getMethod`, and `getConstructor` retrieve appropriate public members; `getDeclaredField`, `getDeclaredMethod`, and `getDeclaredConstructor` retrieve members declared directly on the type under consideration, regardless of modifier.
2. **Performing the operation**: `Field.get`/`set`, `Method.invoke`, and `Constructor.newInstance` must satisfy the caller's access conditions under Java rules and, if applicable, the JPMS module system.

Therefore `SomeType.class.getDeclaredField("secret")` can return a `Field` object for a private field, yet `field.get(target)` or `field.set(target, value)` can still throw `IllegalAccessException`. Similarly, obtaining metadata for a private method/constructor does not automatically grant permission to execute it.

It is also important to distinguish:

- **Where the member is declared**: `getDeclaringClass()` indicates the actual declaring type. An inherited public member can appear via `getMethods()` even though it is not present in the subclass's `getDeclaredMethods()`.
- **Which modifiers the member has**: `getModifiers()` combined with `Modifier.isPublic`, `isPrivate`, ... describes modifiers but does not fully answer whether the current caller may use it.
- **Whether the caller can access it right now**: `canAccess(receiver)` checks current permission on the reflection object (including override state); the actual operation can still fail with additional errors.

## 2. Operations that enforce access checks

| Reflection object | Operation | Receiver requirement | If access is blocked |
| --- | --- | --- | --- |
| `Field` | `get`, `set`, plus `getInt`, `setInt`, ... variants | Suitable instance for instance fields; `null` for static fields | `IllegalAccessException` |
| `Method` | `invoke` | Suitable instance for instance methods; `null` for static methods | `IllegalAccessException` |
| `Constructor<T>` | `newInstance` | Takes no receiver; constructor creates a new object | `IllegalAccessException` |

When access-check override has not been enabled, Java applies language access rules (including accessibility of the **declaring class** and the member itself): `public`, `protected`, package-private, `private`, package context, superclass/subclass, and the caller's location. For named modules, whether the package is `exports`/`opens` to whom must also be considered.

**Note:** Metadata lookup APIs can throw `NoSuchFieldException` or `NoSuchMethodException` if the name/signature does not match; that differs from `IllegalAccessException`, which occurs when using a member that was already found. The operations `get`/`set`/`invoke`/`newInstance` also check receiver type, argument types, assignment constraints, and other runtime conditions. Do not lump all errors under "no permission".

## 3. Complete Java 17+ example with deterministic output

Create a file `AccessCheckDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessCheckDemo {
    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();
        Class<AccessTarget> type = AccessTarget.class;

        Field publicField = type.getField("label");
        Field privateField = type.getDeclaredField("secret");
        Method privateMethod = type.getDeclaredMethod("reveal");
        Constructor<AccessTarget> privateConstructor =
                type.getDeclaredConstructor(String.class);

        System.out.println("public canAccess: " + publicField.canAccess(target));
        System.out.println("public get: " + publicField.get(target));

        System.out.println("private field canAccess: "
                + privateField.canAccess(target));
        try {
            privateField.get(target);
        } catch (IllegalAccessException e) {
            System.out.println("private get blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateField.set(target, "changed");
        } catch (IllegalAccessException e) {
            System.out.println("private set blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateMethod.invoke(target);
        } catch (IllegalAccessException e) {
            System.out.println("private invoke blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateConstructor.newInstance("from private ctor");
        } catch (IllegalAccessException e) {
            System.out.println("private ctor blocked: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("enable field: " + privateField.trySetAccessible());
        System.out.println("enable method: " + privateMethod.trySetAccessible());
        System.out.println("enable ctor: " + privateConstructor.trySetAccessible());

        privateField.set(target, "changed");
        System.out.println("private get after enable: "
                + privateField.get(target));
        System.out.println("private invoke after enable: "
                + privateMethod.invoke(target));
        System.out.println("ctor after enable: "
                + privateConstructor.newInstance("from private ctor").label);
    }
}

class AccessTarget {
    public String label = "visible";
    private String secret = "before";

    public AccessTarget() {
    }

    private AccessTarget(String value) {
        label = value;
        secret = "new-secret";
    }

    private String reveal() {
        return secret;
    }
}
~~~

The two classes are two **top-level classes** in the same default package. This layout is intentional: if `AccessTarget` were placed as a nested class inside `AccessCheckDemo`, the *nestmate* relationship could make private access valid and would no longer accurately illustrate the blocked-access case.

Compile and run:

~~~bash
javac --release 17 AccessCheckDemo.java
java AccessCheckDemo
~~~

Output on a typical classpath/unnamed module:

~~~text
public canAccess: true
public get: visible
private field canAccess: false
private get blocked: IllegalAccessException
private set blocked: IllegalAccessException
private invoke blocked: IllegalAccessException
private ctor blocked: IllegalAccessException
enable field: true
enable method: true
enable ctor: true
private get after enable: changed
private invoke after enable: changed
ctor after enable: from private ctor
~~~

### Reading the output

- `label` is a `public` field; the calling code is in the same package as the top-level class `AccessTarget`. `canAccess(target)` returns `true` and `get(target)` reads the value.
- `secret` is a `private` field of another top-level class. Even though `getDeclaredField` finds the metadata, both `get` and `set` throw `IllegalAccessException` before performing the operation.
- The `reveal` method and the constructor taking `String` are also private. `getDeclaredMethod` and `getDeclaredConstructor` find the members, but `invoke` and `newInstance` are initially blocked.
- In the classpath environment of the example, `trySetAccessible` enables the override for each reflection object. Afterwards, `privateField.set`, `privateField.get`, `privateMethod.invoke`, and `privateConstructor.newInstance` run successfully.
- The private constructor assigns the parameter to `label`, so the new object prints `from private ctor`. The earlier `target` object is still used to read the `reveal()` method after the `secret` field is set to `changed`.

The `javac --release 17` command in the example uses syntax and APIs available since Java 17. Override enablement results may differ in a named module application because of module boundaries.

## 4. Exceptions: access blocked or execution error?

| Exception / result | When it can occur | Practical meaning |
| --- | --- | --- |
| `IllegalAccessException` | `get`, `set`, `invoke`, `Constructor.newInstance` when the caller lacks permission | Not yet allowed to access the member; check access modifiers, declaring class, package, and JPMS |
| `InaccessibleObjectException` | `setAccessible(true)` when the override cannot be enabled | Deep reflection is prevented by module boundaries |
| `trySetAccessible() == false` | Override is not granted | Must handle the failure branch before operating on the private member |
| `NoSuchFieldException` / `NoSuchMethodException` | Lookup with wrong name, signature, or `getX`/`getDeclaredX` scope | Member was not found; not yet an access check result at operation time |
| `IllegalArgumentException` | Wrong receiver, wrong argument types/count, incompatible assignment value | Fix the receiver, parameter types, and value |
| `InvocationTargetException` | `Method.invoke` or `Constructor.newInstance` invokes target code and target code throws an exception | Inspect `getCause()` to distinguish logic errors in the method/constructor |
| `InstantiationException` | Constructor reflection tries to instantiate a non-instantiable class (e.g., abstract class) | Class type cannot be instantiated per contract |
| `final field` issues | Final fields have dedicated write restrictions, even when override is enabled | Do not rely on reflective writes to mutate immutable state |

`InvocationTargetException` is not a sign of missing access permission: usually the method or constructor **was already invoked** and the exception originated from the target code body. When calling `Method.invoke` on an instance method, dynamic dispatch can still happen according to Java rules; using `getDeclaringClass()` does not mean forcing invocation of a superclass implementation.

For final fields, distinguish read access from write access. Certain final fields such as `static final`, final fields of records, and final fields in hidden classes are **non-modifiable final fields**; `setAccessible(true)` may allow reading them but does not make the field writable. Even when mechanisms exist to write other final fields, relying on them breaks invariants/optimizations and should not be used for business logic.

## 5. Self-check exercises

**Question 1.** Why does `getDeclaredField("secret")` return a `Field` object while `get` fails with `IllegalAccessException`? Because `getDeclaredField` only looks up metadata of a directly declared field; `get` is an operation that uses the member and requires access permission.

**Question 2.** `trySetAccessible()` returns `true` in the example but `false` in another application—is there a contradiction? No. Package/module and caller conditions differ; an unnamed module on the classpath and an encapsulated named module have different boundaries.

**Question 3.** `Method.invoke` throws `InvocationTargetException`—does that mean missing permission? You should not conclude that. Inspect `getCause()` to understand the error thrown by the invoked method; missing reflective access permission is represented by `IllegalAccessException`.

**Question 4.** Why does enabling `setAccessible(true)` not necessarily allow modifying `static final`? Because the override only affects the access check; `final` also carries its own restrictions on write permission, and some final fields cannot be modified via Reflection at all.

When working with Reflection, evaluate independently: **find member → check actual permission → perform operation → handle operation and target-code errors**; this prevents confusing lookup errors, access permission errors, argument errors, and business-logic errors.