# Multiple Interfaces with Matching Method Signatures in Java Dynamic Proxies

## 1. The problem to understand

A dynamic proxy created with `java.lang.reflect.Proxy` can implement **multiple interfaces** simultaneously. What happens if those interfaces declare methods with the **same name and same parameter type list**?

For example, both `Readable` and `Auditable` have `String status()`:

~~~java
interface Readable {
    String status();
}
interface Auditable {
    String status();
}
~~~

On the caller side, the same proxy can be cast to `Readable` or `Auditable` and `status()` called. However, the generated proxy class has only a single shared dispatch mechanism; it **receives no information about which interface the caller cast the object to**. Therefore, `InvocationHandler.invoke(proxy, method, args)` cannot rely on the variable type at the call site to know "did the call come from Readable or Auditable?"

Key points to master:

- **Interface order when creating the proxy matters.** For methods with the same name and parameters, the proxy prefers the `Method` from the interface appearing earliest in the interface array (including methods inherited by that interface), when methods are merged with the same return type.
- **Return types must be compatible** for the proxy to be created at all. Reference return types may be covariant; primitive or `void` types must match exactly.
- **Checked exceptions must be valid for all related declarations**; otherwise, the proxy may wrap the exception in `UndeclaredThrowableException`.
- **Default methods do not run automatically** just because an interface has a body. A handler wanting to use a default implementation must select and invoke it intentionally.
- Certain cases with differing return types require further distinction by JVM-level signature; do not mechanically infer that all same-named calls dispatch to the exact same `Method`.

## 2. What does "matching signature" mean?

At the Java source level, a **method signature** consists of the method name and parameter types (plus method type parameters if any); **return type and `throws` do not participate in overloading**. Thus:

| Interface A | Interface B | Relationship |
| --- | --- | --- |
| `String name()` | `String name()` | Same name, parameters, and return type |
| `Number id()` | `Integer id()` | Same name/parameters, covariant return types |
| `void send(String s)` | `void send(String s) throws IOException` | Same name/parameters, different `throws` |
| `void send(String s)` | `void send(int n)` | **Different** signatures because parameter types differ |
| `int count()` | `long count()` | Same name/parameters but incompatible primitive return types |

A proxy can serve calls from multiple interfaces. However, validation at proxy creation and dispatch into the handler follow `Proxy`'s own rules; it is not identical to manually writing `class implements A, B` in source code.

## 3. Interface order determines the `Method` seen in the handler

Create a proxy with:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[] { Readable.class, Auditable.class },
        handler);
~~~

When both interfaces have the exact `String status()`, calls via `((Readable) proxy).status()` and `((Auditable) proxy).status()` both route to the handler with the same **representative method**: `Readable.status()`, because `Readable` comes first. Reversing the array order selects `Auditable.status()`. The order does not change the static call type at compile time; it changes how the generated proxy executes and which `Method` is chosen.

An easily missed detail: if the earlier interface **inherits** the method from a parent interface, `method.getDeclaringClass()` may return **the actual declaring parent interface**, rather than the interface directly placed in the array. Thus, `getDeclaringClass()` is not guaranteed to always be an element of the interface array.

### Runnable example: swapping order and casting through two interfaces

Create the file `DuplicateMethodDemo.java`:

~~~java
import java.lang.reflect.Proxy;

public class DuplicateMethodDemo {
    public interface Readable { String status(); }
    public interface Auditable { String status(); }

    static Object makeProxy(Class<?> first, Class<?> second) {
        return Proxy.newProxyInstance(
                DuplicateMethodDemo.class.getClassLoader(),
                new Class<?>[] { first, second },
                (proxy, method, args) -> {
                    if (method.getName().equals("status")) {
                        System.out.println("Method from: "
                                + method.getDeclaringClass().getSimpleName());
                        return "READY";
                    }
                    throw new UnsupportedOperationException(method.toString());
                });
    }

    public static void main(String[] args) {
        Object first = makeProxy(Readable.class, Auditable.class);
        System.out.println(((Readable) first).status());
        System.out.println(((Auditable) first).status());

        Object reversed = makeProxy(Auditable.class, Readable.class);
        System.out.println(((Readable) reversed).status());
    }
}
~~~

Run with Java 17+:

~~~bash
javac DuplicateMethodDemo.java
java DuplicateMethodDemo
~~~

Output:

~~~text
Method from: Readable
READY
Method from: Readable
READY
Method from: Auditable
READY
~~~

The first two calls use different reference types yet the handler still sees `Readable`. The third call shows that **interface registration order** changes the `Method` passed to the handler. **Do not branch business logic based on the cast type at the caller**, because the handler does not have that information.

## 4. Return type compatibility rules

For methods with the same name and same parameter list, `Proxy.newProxyInstance` requires return types to satisfy these conditions:

1. If **any** return type is primitive or `void`, **all must be that exact type**. `int` and `long`, or `void` and `Object`, cannot be merged; there is no autoboxing or widening to legalize the proxy.
2. If all are **reference types**, there must exist one return type assignable to **all** the remaining return types. For instance, `Integer` is a subtype of `Number`, so `Number code()` and `Integer code()` are compatible. Two unrelated leaf types `String` and `Integer` have no suitable subtype relationship and are incompatible.
3. When the condition is not satisfied, the **proxy creation** call throws `IllegalArgumentException`; it does not wait until a method is invoked.

**Subtlety with covariant returns:** `Number code()` and `Integer code()` have the same name/parameters from a Java perspective, but have **different JVM descriptors because descriptors include the return type**. The proxy class may generate the necessary methods/bridges; in Java 17, the handler may see a `Method` with return type `Number` when called through the wider interface and `Integer` when called through the narrower interface. Thus, the "first interface wins" rule does not mean `method.getReturnType()` is always identical when covariant returns exist. Test specific behavior and always return an object compatible with all relevant contracts.

**Value returned by the handler:** the proxy checks/casts to the corresponding return type. Returning the wrong reference type causes `ClassCastException`; returning `null` for a primitive return type can cause `NullPointerException` during unboxing. `void` typically requires the handler to return `null` (the handler's return value will be ignored).

## 5. Differing `throws`: only the common checked exception set is safe

Two interfaces may both declare `read()`, yet one interface `throws IOException` and the other `throws SQLException`. **Proxy creation is still valid**, because `throws` is not part of the return type and does not determine runtime signatures. However, the handler **is not free to throw every checked exception from the earlier interface**.

Rule: for a checked exception to pass through the proxy without being wrapped, that exception type must be compatible with at least one exception declared in **each** matching-signature method across the relevant interfaces. If one interface declares `Exception` and another declares `IOException`, `IOException` can pass through; `SQLException` does not satisfy the second interface. If one declares `IOException` and the other declares `SQLException`, a regular `IOException` cannot pass directly through both contracts.

If the handler throws a checked exception invalid against the combined contracts, the proxy wraps it in **`java.lang.reflect.UndeclaredThrowableException`**, which is an unchecked exception. Use `getUndeclaredThrowable()` or `getCause()` to inspect the cause.

`RuntimeException` and `Error` are not subject to `throws` declaration restrictions like checked exceptions; they propagate outward under normal unchecked rules. Distinguish runtime errors thrown by the handler from proxy creation errors (typically `IllegalArgumentException`).

## 6. Multiple same-named default methods: choose an implementation explicitly

Java 8 added **default methods** with bodies inside interfaces. When a dynamic proxy implements two interfaces both having `default String label()`, calling `label()` **still goes through `InvocationHandler.invoke`**; the proxy does not automatically choose the first or second interface's body to execute.

Since Java 16, `InvocationHandler.invokeDefault(proxy, method, args...)` lets the handler invoke a specific default method. You can obtain the `Method` from the desired interface, such as `Second.class.getMethod("label")`, and call `invokeDefault`. This is an explicit business decision distinct from the rule governing which `Method` enters the handler. The method to invoke must be a valid, accessible default method declared on a proxy interface or inherited such that it remains selectable under JVM rules. If an interface overrides a default method in the future, an `invokeDefault` call to the older implementation may no longer be valid.

If the first interface declares an abstract method and the second declares a default method with the same name/parameters, it also **does not follow** that the proxy will automatically run the default method. The handler must dispatch explicitly.

## 7. Complete example: return types, checked exceptions, and default methods (Java 17+)

Create the file `ProxyEdgeCases.java`:

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class ProxyEdgeCases {
    public interface Wide { Number code(); }
    public interface Narrow { Integer code(); }
    public interface BadA { int amount(); }
    public interface BadB { long amount(); }
    public interface Disk { String read() throws IOException; }
    public interface Database { String read() throws SQLException; }
    public interface First {
        default String label() { return "first"; }
    }
    public interface Second {
        default String label() { return "second"; }
    }

    public static void main(String[] args) throws Throwable {
        Object covariant = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { Wide.class, Narrow.class },
                (proxy, method, callArgs) -> {
                    System.out.println("Return token: "
                            + method.getReturnType().getSimpleName());
                    return 42;
                });
        System.out.println(((Wide) covariant).code());
        System.out.println(((Narrow) covariant).code());

        try {
            Proxy.newProxyInstance(
                    ProxyEdgeCases.class.getClassLoader(),
                    new Class<?>[] { BadA.class, BadB.class },
                    (proxy, method, callArgs) -> 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Primitive conflict: IllegalArgumentException");
        }

        Object checked = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { Disk.class, Database.class },
                (proxy, method, callArgs) -> { throw new IOException("failed"); });
        try {
            ((Disk) checked).read();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("Wrapped checked: "
                    + ex.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object defaults = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { First.class, Second.class },
                (proxy, method, callArgs) -> {
                    System.out.println("Default Method from: "
                            + method.getDeclaringClass().getSimpleName());
                    Method chosen = Second.class.getMethod("label");
                    return InvocationHandler.invokeDefault(proxy, chosen);
                });
        System.out.println(((First) defaults).label());
        System.out.println(((Second) defaults).label());
    }
}
~~~

Compile and run:

~~~bash
javac ProxyEdgeCases.java
java ProxyEdgeCases
~~~

Verified output on OpenJDK 21 with `javac --release 17`:

~~~text
Return token: Number
42
Return token: Integer
42
Primitive conflict: IllegalArgumentException
Wrapped checked: IOException
Default Method from: First
second
Default Method from: First
second
~~~

Explanation:

- `Wide.code()` and `Narrow.code()` are valid thanks to covariant return types. The two calls receive `Method` with return types `Number` and `Integer` respectively; the handler returns `Integer(42)`, which fits both.
- The two `amount()` declarations with differing primitive return types (`int`/`long`) are rejected **at proxy creation time**.
- The handler throws `IOException` while the proxy also exposes `Database.read() throws SQLException`, so the exception is wrapped even though the call was made through `Disk`.
- On both calls to `label()`, the handler receives `Method` from `First` because `First` was registered first. However, the handler chooses to **execute `Second`'s default implementation**, so both results are `second`.

Note that the output above is the result of **this exact example**; changing interface order, return types, signatures, or handler logic will alter the output.

## 8. Three `Object` methods have special priority

`equals(Object)`, `hashCode()`, and `toString()` are the three public, non-final methods of `Object` routed by dynamic proxies to `InvocationHandler`. If a proxy interface happens to redeclare them with matching signatures, the `Method` passed to the handler still has `getDeclaringClass() == Object.class`, because these methods take **precedence over all interfaces** when selecting `Method`.

Do not apply this reasoning to every `Object` method (for example `getClass()` is final and is not overridden by this mechanism to go to the handler). The handler should handle these three fundamental methods explicitly to avoid unexpected `toString()` output or recursive logging loops:

~~~java
// Fragment inside InvocationHandler.invoke(proxy, method, args)
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "DynamicServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.toString());
    };
}
~~~

This is a **fragment**, not a standalone program. In particular, avoid calling `proxy.toString()` inside the handler's own `toString` branch because it will re-enter the handler.

## 9. Generics, method erasure, and limits of `Method`

At runtime, dynamic proxies work with `Method` and parameter/return types as represented by the JVM. For instance, parameter types `List<String>` and `List<Integer>` share the same raw type `List` after erasure; `Method.getParameterTypes()` typically reports `List.class` without verifying individual elements at runtime.

`Method.getGenericParameterTypes()` can read **generic declaration** info retained in the class file, but that information **does not mean** calls to the proxy are deeply checked by the JVM for `String` or `Integer` elements. When two interfaces have different generic declarations whose erasures collide, you must not route business logic purely on the generic type expected at the caller.

Some specialized generic interfaces may have compiler-generated **bridge methods**, marked by `Method.isBridge()` or `isSynthetic()`. When diagnosing, inspect `method.getName()`, `getParameterTypes()`, `getReturnType()`, and `getDeclaringClass()`, rather than assuming the method name is a unique identifier.

Externally received inputs must still be content-validated; dynamic proxies do not replace generic data validation mechanisms.

## 10. Designing a stable handler when combining multiple interfaces

To avoid confusion and accidental order-dependent behavior:

1. **Audit interfaces before creating the proxy:** collect declared and inherited public methods, group by name + erased parameter list; compare return types, checked exceptions, default implementations, and business meaning.
2. **Specify interface order explicitly** when passing to `Proxy.newProxyInstance`. Do not take an arbitrary order from a `HashSet` or an unordered collection; order is a meaningful input.
3. **Unify business semantics of matching-signature methods** if they are meant to share one behavior. If two interfaces carry two distinct meanings with the same signature, change the design (rename or split proxies) because the handler cannot know the caller's reference type to tell them apart.
4. **Branch by defined contract**, rather than blindly treating `method.getDeclaringClass()` as "the caller's interface." When covariant returns or bridges exist, inspect descriptors/return types as well.
5. **Select default methods explicitly** with `InvocationHandler.invokeDefault` if you genuinely want to run a default body.
6. **Standardize exception handling and return values** across all interfaces. Handle `equals`, `hashCode`, and `toString` separately and avoid uncontrolled re-entry into the proxy.
7. **Ensure the class loader sees all interfaces**, the interfaces are valid proxy types, and declarations have no return-type conflicts; changing array order may generate a different proxy class.

When two different implementations are needed for the same name/parameters based on business context, pass an **explicit context** (parameter, strategy, adapter) or create two separate proxies/entry points. Casting a single proxy through different interfaces does not pass that information into `invoke`.

## 11. Common errors table

| Symptom | Cause | Fix |
| --- | --- | --- |
| Handler always sees interface A even when called through B | A appears earlier in the interface array and methods match | Review registration order; do not infer caller type |
| `IllegalArgumentException` when creating proxy | Return type conflict or proxy creation constraint violated | Check methods with matching name/parameters, return types, and visibility |
| `UndeclaredThrowableException` when calling method | Checked exception from handler invalid against all `throws` | Check `getUndeclaredThrowable()`, unify error contracts |
| Default method does not execute | Every proxy call goes through the handler | Use `InvocationHandler.invokeDefault` with a valid `Method` |
| `method.getReturnType()` differs between two calls | Covariant methods have different return descriptors | Distinguish this case from methods with identical return types |
| `ClassCastException` or `NullPointerException` after `invoke` | Handler returned incompatible type or `null` for primitive | Return exact expected type and check nullability |
| Handler loops infinitely when logging | Handler calls a method on the proxy itself | Do not call `proxy.toString()` from the `toString` branch |

## 12. Self-check questions

1. If both `A` and `B` declare `String name()`, the proxy is created with `[A.class, B.class]`, and it is called via a variable of type `B`, which interface does `Method` belong to? **`A`** (or the actual parent interface declaring the method inherited by `A`), because A comes first.
2. What does swapping to `[B.class, A.class]` affect? **It can change the representative `Method`** for methods with the same descriptor; it does not alter each interface's own method behavior.
3. Can `Number value()` and `Integer value()` be proxied together? **Yes**, because `Integer` is a subtype of `Number`. However, do not assume `Method.getReturnType()` is identical on every call.
4. Can `int value()` and `long value()` be proxied together? **No**; primitive return types must match identically.
5. Why can `throws IOException` and `throws SQLException` lead to `UndeclaredThrowableException`? Because checked exceptions from the handler must be valid against **all contracts** of the matching method; `IOException` is not covered by `throws SQLException`.
6. To run the body of `Second.default label()` when the handler receives `Method` belonging to `First`, what is needed? **Obtain `Second.class.getMethod("label")` and call `InvocationHandler.invokeDefault(proxy, chosen)`** when that method can be validly selected.
7. Can you inspect `method.getDeclaringClass()` to tell whether the caller cast the proxy to A or B? **No**. The proxy class does not pass the caller's reference type into the handler.

## References

- [Oracle JDK 17 — Proxy: Methods Duplicated in Multiple Proxy Interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Oracle JDK 17 — InvocationHandler and invokeDefault](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)

**Takeaway:** When multiple interfaces have methods with matching names and parameters, examine **interface order, return types, checked exceptions, and default methods** as four independent dimensions. The `Method` received in the handler is not information about the caller's variable type. Designing clear contracts before writing dispatch avoids most hard-to-diagnose bugs.