# `canAccess` and the appropriate target object in Java Reflection

## 1. Problem to solve

When using Reflection, obtaining a `Field`, `Method`, or `Constructor` **does not mean the running code is allowed to access that member**. The lookup step (`getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`) and the access check step are two different things.

Since Java 9, `AccessibleObject.canAccess(Object obj)` helps check whether **the current calling code** can access the reflected member, in the context of an **appropriate target object**. The three groups of Reflection objects that support this method are:

- `Field`: a data field, instance or static;
- `Method`: a method, instance or static;
- `Constructor`: a constructor, which has no target instance before instantiation.

Key point: the `obj` argument of `canAccess` is the **target object for evaluating access permission**, not a field value, method argument, or class name. For static members and constructors, `null` must be passed.

## 2. Choosing the right `obj` for the member kind

| Reflection object | Valid `canAccess(obj)` argument | Example |
| --- | --- | --- |
| Instance `Field` | A non-`null` object that is an instance of the field's declaring class or a subclass | `field.canAccess(customer)` |
| Instance `Method` | A non-`null` object that is an instance of the method's declaring class or a subclass | `method.canAccess(customer)` |
| Static `Field` | **`null`** | `field.canAccess(null)` |
| Static `Method` | **`null`** | `method.canAccess(null)` |
| `Constructor` | **`null`** | `ctor.canAccess(null)` |

**Important:** this is a rule specific to `canAccess`. Some other Reflection invocation APIs may have different rules for the target object parameter (for example `Field.get` can ignore the passed object for a static field); do not extrapolate that rule backward onto `canAccess`.

An instance of a **subclass** can still be a valid target object for an instance member declared in a superclass. Having a valid target type is only an **input precondition**; it is not enough to conclude access is permitted. Especially with `protected` across packages, the receiver type can also affect the access check result under Java rules.

### When passing the wrong target object

`canAccess` **throws `IllegalArgumentException`**, rather than returning `false`, if:

1. The member is an **instance field / instance method** and `obj == null`;
2. The member is an instance field / method and `obj` is not an instance of the declaring class (or an appropriate subclass);
3. The member is a **static field / static method / constructor** and `obj != null`.

Therefore, distinguish:

- `false` = the target argument has the right form, but the calling code **lacks access permission** under the current state/rules;
- `IllegalArgumentException` = **the target object passed to `canAccess` is invalid**. This is not an access check result of `false`.

## 3. Whose permission does `canAccess` check?

`canAccess` answers the question: is **the current caller** allowed to access the reflected member on this target object?

The check involves several factors:

- `public`, `protected`, package-private, `private` of the member and accessibility of the declaring class;
- location of the calling code: class, package, inheritance relationship;
- for applications using JPMS (Java Platform Module System): module boundaries, whether the package is `exports` or `opens`, depending on the type of access used;
- the flag that suppresses Java language access control checks on that specific `Field`/`Method`/`Constructor` object, enabled when `trySetAccessible()` or `setAccessible(true)` succeeds;
- the target object's type, especially the receiver rule for `protected` members in certain cross-package inheritance cases.

If the access-check suppression flag has been successfully enabled, `canAccess` returns `true` when `obj` is valid. If the flag is not enabled, it checks the caller's permission under Java access control (Reflection has specific adjustments for module readability per the Javadoc).

**Do not treat `canAccess` as a fixed property of a `Field` or `Method` alone.** When called from different classes, the result can differ because the caller changes. Passing a `Method` to a helper and calling `canAccess` inside the helper also ties the check context to the helper, without automatically transferring the original caller's permissions.

## 4. Standalone runnable Java 17+ example

Save as `CanAccessDemo.java`. The two classes `CanAccessDemo` and `AccessTarget` are **two different top-level classes** in the same file and default package; because of this, the `private` example is not affected by the nestmate relationship of nested classes.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class CanAccessDemo {
    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();

        Field publicField =
                AccessTarget.class.getDeclaredField("count");
        Field privateField =
                AccessTarget.class.getDeclaredField("secret");
        Field staticField =
                AccessTarget.class.getDeclaredField("total");
        Method instanceMethod =
                AccessTarget.class.getDeclaredMethod("ping");
        Method staticMethod =
                AccessTarget.class.getDeclaredMethod("reset");
        Constructor<AccessTarget> constructor =
                AccessTarget.class.getDeclaredConstructor();

        // Instance member: pass a valid target instance.
        System.out.println("public field: " + publicField.canAccess(target));
        System.out.println("instance method: " + instanceMethod.canAccess(target));

        // Static member and constructor: pass null.
        System.out.println("static field: " + staticField.canAccess(null));
        System.out.println("static method: " + staticMethod.canAccess(null));
        System.out.println("constructor: " + constructor.canAccess(null));

        // Valid target but private: caller has no default permission.
        System.out.println("private before: " + privateField.canAccess(target));

        try {
            publicField.canAccess(null);
        } catch (IllegalArgumentException e) {
            System.out.println("instance + null: IllegalArgumentException");
        }

        try {
            publicField.canAccess(new Object());
        } catch (IllegalArgumentException e) {
            System.out.println("instance + wrong type: IllegalArgumentException");
        }

        try {
            staticField.canAccess(target);
        } catch (IllegalArgumentException e) {
            System.out.println("static + non-null: IllegalArgumentException");
        }

        try {
            constructor.canAccess(target);
        } catch (IllegalArgumentException e) {
            System.out.println("constructor + non-null: IllegalArgumentException");
        }

        // Two classes in the same unnamed module: permission can be enabled in this example.
        boolean enabled = privateField.trySetAccessible();
        System.out.println("opened private: " + enabled);
        System.out.println("private after: " + privateField.canAccess(target));

        if (privateField.canAccess(target)) {
            System.out.println("secret value: " + privateField.get(target));
        }
    }
}

class AccessTarget {
    public int count = 3;
    private String secret = "demo";
    public static int total = 9;

    public AccessTarget() { }

    public void ping() { }

    public static void reset() { }
}
~~~

Run:

~~~bash
javac CanAccessDemo.java
java CanAccessDemo
~~~

Output on JDK 17+ when the two classes are run in the same unnamed module (as in the command above):

~~~text
public field: true
instance method: true
static field: true
static method: true
constructor: true
private before: false
instance + null: IllegalArgumentException
instance + wrong type: IllegalArgumentException
static + non-null: IllegalArgumentException
constructor + non-null: IllegalArgumentException
opened private: true
private after: true
secret value: demo
~~~

**Explanation:**

1. Field `count` and method `ping` are public, `CanAccessDemo` code is in the same package as `AccessTarget`, and `target` is a valid instance: `canAccess(target)` returns `true`.
2. `total` and `reset` are static; the constructor has no target instance: `canAccess(null)` must be used.
3. `secret` is `private` to **another top-level class**. Caller `CanAccessDemo` does not have default access, so the result is `false` even though `target` has the right type.
4. The four calls inside `try` blocks intentionally violate the `obj` parameter rule. Each call triggers `IllegalArgumentException` before reaching a conclusion on whether access is permitted.
5. `trySetAccessible()` succeeds in this same-unnamed-module example; the flag state enables bypassing language access checks, so `canAccess(target)` changes to `true` and `Field.get(target)` can read the private field. That **does not guarantee success across all modules or all members**.

## 5. How to use `canAccess` together with `trySetAccessible`

`canAccess(obj)` is a **check**; it does not change access permission itself. `trySetAccessible()` is a **request to enable the access-check suppression flag** if allowed:

~~~java
// Illustration in an existing context:
// Field field = ...; Object receiver = ...; receiver has the right type.
if (!field.canAccess(receiver)) {
    if (!field.trySetAccessible()) {
        throw new IllegalAccessException("Cannot enable Reflection access");
    }
}
Object value = field.get(receiver);
~~~

This snippet is an **illustration inside a method that handles/declares checked exceptions**; it is not a standalone program. Only request opening access for members that the application is permitted and genuinely needs to access.

- `canAccess` does not open access; `false` does not imply `trySetAccessible` will definitely succeed.
- `trySetAccessible` returns `true` if the flag could be enabled; it returns `false` when it cannot be enabled due to normal access restrictions, such as another module's package not being appropriately opened to the caller. It can still throw `SecurityException` in an environment enforcing a Security Manager.
- `setAccessible(true)` has a similar goal, but can throw `InaccessibleObjectException` if the flag cannot be enabled due to module encapsulation restrictions.
- `isAccessible()` has been deprecated since Java 9. Its name is misleading: it only reflects the access-check suppression flag and does **not** fully answer whether the caller has permission to access. Use `canAccess` for checking current access permission.
- `canAccess` returning `true` does not mean the next operation is guaranteed to succeed, because other conditions remain: arguments to `Method.invoke`, data types in `Field.set`, `final` status, exceptions from the target method, and other runtime factors.

### Easily confused states

| Case | Typical result | Reason |
| --- | --- | --- |
| Public instance field, matching receiver type, accessible class/package | `true` | Caller has normal permission. |
| Private instance field of another top-level class, matching receiver type | `false` | Receiver is valid, but permission is restricted. |
| Instance field, `null` receiver | `IllegalArgumentException` | Wrong target object kind. |
| Instance method, receiver not of declaring class or subclass | `IllegalArgumentException` | Wrong target object kind. |
| Static method, receiver is an object | `IllegalArgumentException` | Static requires `null`. |
| Constructor, receiver is an object | `IllegalArgumentException` | Constructor requires `null`. |
| Private field, `trySetAccessible()` succeeded, matching receiver type | `true` | Access-check suppression flag is enabled. |

## 6. Pitfalls in real-world code

### Confusing the `canAccess` argument with `invoke` arguments

For an instance method:

~~~java
Method m = String.class.getMethod("substring", int.class);
String receiver = "reflection";

System.out.println(m.canAccess(receiver)); // true
System.out.println(m.invoke(receiver, 3));  // lection
~~~

`canAccess(receiver)` takes the **receiver**, not `3`. `invoke(receiver, 3)` takes the receiver **and** the argument passed to `substring`. Calling `m.canAccess(3)` passes an `Integer` instead of a `String`, throwing `IllegalArgumentException`. The illustrative snippet above must be placed in a method that handles/declares checked exceptions.

### Confusing `null` on a constructor with not being allowed to create an instance

`constructor.canAccess(null)` only checks permission for the constructor. `null` is the required value for the check parameter, **not an argument passed to the constructor**. When you want to create an instance, call `constructor.newInstance(args...)` with the real arguments and handle appropriate exceptions.

### Skipping type checks before permission checks

If writing a shared utility to perform Reflection calls, first determine whether it is static or a constructor, then validate the receiver:

~~~java
// Sketch applicable when AccessibleObject member is already available.
if (member instanceof Constructor<?>) {
    // canAccess(null)
} else if (member instanceof Field field) {
    // Modifier.isStatic(field.getModifiers()) ? null : receiver
} else if (member instanceof Method method) {
    // Modifier.isStatic(method.getModifiers()) ? null : receiver
}
~~~

The snippet above describes logic, not a complete function. For an instance member, check `receiver != null` and `declaringClass.isInstance(receiver)` before calling `canAccess(receiver)`, so target-data errors are reported clearly. `Class.isInstance` handles subclass instances, rather than only comparing exact `receiver.getClass() == declaringClass`.

### Misunderstanding modules and `public`

A `public` method is not automatically accessible from every module if the declaring class or package is not appropriately exported. Conversely, metadata can be obtained with `getDeclaredMethod` without yet having permission to `invoke`. When an application runs across different named modules, `exports` relates to using public APIs; `opens` relates to performing deep reflection. Opening with `trySetAccessible` must not be viewed as a way to bypass all module boundaries.

## 7. Step-by-step `canAccess` decision checklist

1. **Identify the member kind:** `Field`, `Method`, or `Constructor`.
2. **Determine static vs instance:** `Modifier.isStatic(member.getModifiers())` applies to fields/methods.
3. **Choose the receiver:** static/constructor → `null`; instance → an object of the declaring class or a subclass.
4. **Call `canAccess(receiver)`:** handle separately the case where an invalid receiver causes `IllegalArgumentException`.
5. **If it returns `false`:** examine class/package/module permissions and application policy; consider `trySetAccessible()` only when needed and allowed.
6. **Execute Reflection:** `Field.get/set`, `Method.invoke`, or `Constructor.newInstance`; continue handling operation-specific errors.

### Self-check

- You have a private instance `Field`; you pass an instance of the right class to `canAccess` without having opened access. What is the result? **Usually `false` if the caller lacks permission**, not `IllegalArgumentException`.
- You have a public static `Method`; what happens if you call `canAccess(new Object())`? **`IllegalArgumentException`**, because static requires passing `null`.
- You have an instance `Field` declared in `Base`, and the actual object is `Derived extends Base`. Is the receiver valid? **Yes**; only after that is the caller's access permission evaluated.
- If `trySetAccessible()` returns `false`, should you call `get` on a private field as if access had been opened? **No**; you must handle the lack of permission or change the design/API.

**Conclusion:** `canAccess(obj)` requires **the right target object first**, and only then evaluates **the caller's permission**. `false` indicates access is not permitted with a valid target object; a wrong target type causes `IllegalArgumentException`. Static members and constructors must pass `null`.

### Official documentation

- [JDK 17 — AccessibleObject.canAccess(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#canAccess(java.lang.Object))
- [JDK 17 — AccessibleObject.trySetAccessible()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible())
- [JDK 17 — java.lang.reflect.Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Java Language Specification §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)