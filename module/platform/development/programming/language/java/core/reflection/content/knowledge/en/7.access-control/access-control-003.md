# AccessibleObject and bypassing access checks in Java Reflection

Reflection allows finding `Field`, `Method`, and `Constructor` even when the member is not `public`. However, **finding metadata does not mean being permitted to read a field, invoke a method, or create an object**. `java.lang.reflect.AccessibleObject` is the superclass of those three Reflection object types, providing APIs to check access permission and, when allowed, enable **suppressing Java language access checks**.

This topic belongs to the **Access control** group. The goal is to understand the accessible flag accurately, know when to use `canAccess`, `setAccessible`, and `trySetAccessible`, and understand why Java 9+ module boundaries can block enabling the flag. The examples use Java 17+.

## 1. Role and main APIs

```text
java.lang.reflect.AccessibleObject
  ├── java.lang.reflect.Field
  └── java.lang.reflect.Executable
        ├── java.lang.reflect.Method
        └── java.lang.reflect.Constructor
```

| API | Meaning |
| --- | --- |
| `boolean canAccess(Object obj)` | Reports whether the current caller can access the represented member, considering the receiver and current state |
| `void setAccessible(boolean flag)` | Sets the flag requesting access checks to be suppressed; enabling `true` succeeds only if Java/module rules allow it |
| `boolean trySetAccessible()` | Attempts to enable the flag; returns `true` if successful, `false` if it cannot be enabled due to access restrictions |
| `boolean isAccessible()` | Legacy API, deprecated since Java 9; **only** reflects the access-check suppression flag, and does not fully answer whether the caller can access the member |
| `static void setAccessible(AccessibleObject[] array, boolean flag)` | Sets the flag for multiple Reflection objects, still subject to permission/module checks |

The methods `Class.getDeclaredField`, `getDeclaredMethod`, and `getDeclaredConstructor` can return `private`, `protected`, or package-private members of that class itself, but **do not automatically enable the flag**. The APIs `getField`, `getMethod`, and `getConstructor` look up `public` members within their respective scopes; even for a `public` member, the module or declaring class still affects accessibility from the caller.

## 2. Distinguishing three commonly conflated concepts

**Member visibility** is `public`, `protected`, package-private, or `private` in source code and bytecode. Reflection does not change this visibility.

**Accessible flag state** is an option on a specific `Field`, `Method`, or `Constructor` object to suppress access checks when using that very Reflection object. By default, the flag is `false`. A successful `setAccessible(true)` or `trySetAccessible()` enables the flag; `setAccessible(false)` disables it.

**Actual access permission** is checked based on the caller, member kind, receiver, flag, and module boundaries. This is the meaning of `canAccess(obj)`. A `public` method can have the flag set to `false` while `canAccess(receiver) == true`, because the caller already has permission under normal rules. Conversely, finding a `private` member with `getDeclaredMethod` does not mean `invoke` will be allowed.

Therefore:

- `isAccessible() == false` does **not** mean "the member is inaccessible".
- `canAccess(obj)` does not enable access permission; it only checks it.
- `setAccessible(true)` does not turn a member into `public` and does not bypass all Java Platform Module System (JPMS) limits.
- `setAccessible(false)` does not forbid a caller from using a member the caller already has permission to access.

## 3. Compilable and runnable Java 17+ example

Create a single file `AccessibleObjectDemo.java` as follows. `Vault` is a **separate top-level class**, in the same file/package as the demo class, not a nested class. This layout avoids the **nestmates** effect: nested classes in the same nest can access each other's `private` members under modern Java rules, which would distort expectations when demonstrating a lack of access permission.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessibleObjectDemo {
    public static void main(String[] args) throws Exception {
        Constructor<Vault> ctor = Vault.class.getDeclaredConstructor();
        System.out.println("constructor.before=" + ctor.canAccess(null));
        System.out.println("constructor.try=" + ctor.trySetAccessible());

        Vault vault = ctor.newInstance();
        System.out.println("constructor.after=" + ctor.canAccess(null));

        Field secret = Vault.class.getDeclaredField("secret");
        System.out.println("field.before=" + secret.canAccess(vault));

        try {
            secret.get(vault);
        } catch (IllegalAccessException e) {
            System.out.println("field.get.before=IllegalAccessException");
        }

        secret.setAccessible(true);
        System.out.println("field.after=" + secret.canAccess(vault));
        System.out.println("field.value=" + secret.get(vault));

        secret.setAccessible(false);
        System.out.println("field.reset=" + secret.canAccess(vault));

        Method reveal = Vault.class.getDeclaredMethod(
                "reveal", String.class);
        System.out.println("method.before=" + reveal.canAccess(vault));
        System.out.println("method.try=" + reveal.trySetAccessible());
        System.out.println("method.result="
                + reveal.invoke(vault, "key="));

        Method status = Vault.class.getDeclaredMethod("status");
        System.out.println("public.canAccess=" + status.canAccess(vault));
    }
}

class Vault {
    private final String secret;

    private Vault() {
        this.secret = "s3";
    }

    private String reveal(String prefix) {
        return prefix + secret;
    }

    public String status() {
        return "READY";
    }
}
```

In a terminal in the directory containing the file:

```bash
javac AccessibleObjectDemo.java
java AccessibleObjectDemo
```

Standard output in the example running on the classpath (unnamed module):

```text
constructor.before=false
constructor.try=true
constructor.after=true
field.before=false
field.get.before=IllegalAccessException
field.after=true
field.value=s3
field.reset=false
method.before=false
method.try=true
method.result=key=s3
public.canAccess=true
```

**Explanation:**

1. `Vault()` is a `private` constructor. `getDeclaredConstructor()` still finds its metadata, but `canAccess(null)` is initially `false` for caller `AccessibleObjectDemo`. After `trySetAccessible()` returns `true`, `newInstance()` can create the object.
2. `secret` is a `private final` field. `getDeclaredField` finds it, but `Field.get` is blocked before enabling the override, throwing `IllegalAccessException`.
3. `setAccessible(true)` enables the flag on the `Field secret` object, allowing **reading** the value `s3`. The example does not attempt to modify a `final` field.
4. `setAccessible(false)` disables the override; because the caller is in a different class from the declaring class, `canAccess(vault)` returns to `false`.
5. Method `reveal(String)` is `private` and needs the flag enabled before calling `invoke`. Method `status()` is `public`, and the two classes are in the same package, so it can be accessed normally without enabling the flag.

Note: exact behavior depends on class, package, module, and caller relationships. Do not use the result of an example running on the classpath to conclude that every `private` member in another module can be opened.

## 4. setAccessible, trySetAccessible, and resetting the flag

### setAccessible(true)

`member.setAccessible(true)` requests skipping Java access checks when operating via **that member**. If permitted, subsequent operations such as `Field.get`, `Method.invoke`, or `Constructor.newInstance` can use the override; if blocked by JPMS, it typically throws `java.lang.reflect.InaccessibleObjectException`, an **unchecked exception**.

```java
// Illustrative snippet, assuming method and receiver are already declared,
// method takes no parameters, and code is in an exception-handling context.
try {
    method.setAccessible(true);
    Object result = method.invoke(receiver);
} catch (java.lang.reflect.InaccessibleObjectException e) {
    System.out.println("Package/module is not open for deep reflection");
} catch (ReflectiveOperationException e) {
    System.out.println("Reflection operation failed: " + e);
}
```

The snippet above is not a standalone runnable program. `invoke` can also throw `IllegalArgumentException` when the receiver/arguments are invalid; `InvocationTargetException` wraps exceptions thrown by the target method. Do not treat every error at `invoke` as a permission error.

### trySetAccessible()

`trySetAccessible()` is suitable when an application wants controlled fallback:

```java
// Illustration inside a method that handles invoke's exceptions.
if (method.trySetAccessible()) {
    Object result = method.invoke(receiver);
    System.out.println(result);
} else {
    System.out.println("Could not enable Reflection access");
}
```

Returning `true` means the flag was enabled successfully or was already enabled. Returning `false` means it could not be enabled under current access conditions, for example when a package of another module is not open to the caller. `trySetAccessible()` **can still throw `SecurityException`** in an environment with corresponding security controls; it should not be interpreted as an API that "never throws".

### setAccessible(false)

Calling `member.setAccessible(false)` disables the override flag on that Reflection object. On subsequent operations, normal access-check rules apply again. A `public` member that was already accessible remains accessible. You should not expect this operation to change visibility or revoke permissions of other code.

### isAccessible() is deprecated

`isAccessible()` only returns the state of the **suppress access checks flag**, which makes the method name misleading. It has been deprecated since Java 9. Use `canAccess(receiver)` to ask whether the current caller can access it; use `trySetAccessible()` to check and attempt enabling the flag when needed. A `public` member with `isAccessible() == false` can still have `canAccess(receiver) == true`.

## 5. Boundaries of the accessible flag in applications

The access-check suppression flag applies only to a specific Reflection object; it does not change the class's modifiers or open a package JVM-wide. If the caller belongs to another named module and the package is not opened with the right scope, `trySetAccessible()` can return `false` and `setAccessible(true)` can throw `InaccessibleObjectException`. `exports` for public APIs differs from `opens` for deep reflection.

Having the flag enabled also does not resolve receiver errors, argument type errors, method logic errors, or write restrictions on `final` fields. For normal needs, prefer public APIs. When deep reflection is necessary, identify the owning package/module and handle the denied branch intentionally.

**Self-check:** Why can a `public` method have `canAccess(receiver) == true` while the accessible flag is still `false`? Why does `setAccessible(false)` not turn a public method into a private one? Why does being able to read a private final field not prove that you can modify it?