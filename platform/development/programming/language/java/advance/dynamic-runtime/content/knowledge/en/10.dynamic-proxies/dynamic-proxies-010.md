# 10.10. Duplicate Methods Across Multiple Interfaces, Interface Order, and Throws Restrictions

## Learning Objectives

After this lesson, you will be able to:

1. Understand the mechanism of **JDK dynamic proxy** when a proxy object simultaneously implements multiple interfaces that have **methods with the same name and the same parameter type list**.
2. Explain why the **order of interfaces** in `Proxy.newProxyInstance(...)` determines which `Method` object is passed into `InvocationHandler.invoke(...)`, **regardless of the reference type used for the call** in the case where duplicate methods have the same JVM type.
3. Know the special exception for `equals`, `hashCode`, and `toString` (`java.lang.Object` takes precedence), and the effect when a method comes from a parent interface.
4. Accurately apply the **checked exceptions restriction**: the handler is only allowed to let a checked throwable escape directly if it is compatible with the **throws clauses of all duplicate methods**; if violated, the proxy throws `UndeclaredThrowableException`.
5. Check the **return type** compatibility condition when creating a proxy (primitive/`void` must match; reference types need a compatible return type), and understand the consequence if the handler returns an incorrect value.
6. Write and run a Java 17+ example illustrating interface order, overlapping/disjoint checked exceptions, covariant returns, `Object` methods, and the double-wrapping error when delegating via reflection.
7. Design an `InvocationHandler` that does not mistakenly rely on `Method.getDeclaringClass()` to guess the interface type the caller used.

**Context:** Java dynamic proxy belongs to `java.lang.reflect.Proxy`, not a subclass generated from a specific target. A proxy implements a list of **interfaces** and forwards calls to an `InvocationHandler`. When combining multiple APIs, clients, interceptors, or facet interfaces into the same proxy, duplicate signatures can create unintuitive rules, especially with `throws`.

## 1. Review of the JDK Dynamic Proxy Mechanism

Creating a basic proxy:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

interface Greeting {
    String say(String name);
}

InvocationHandler handler = (proxy, method, args) ->
        "Hello, " + args[0];

Greeting greeting = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

This is an **illustrative snippet**; the variable initialization needs to be placed inside a method or initializer; section 7 has a standalone runnable program.

At runtime, the Java-generated proxy class:
- implements the exact interfaces provided (and in **that order**);
- forwards interface calls to `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`;
- uses `method` to represent the dispatched method, and `args` contains the boxed arguments if primitive (for a zero-argument method, `args` may be `null`);
- takes the `Object` returned by the handler and checks/converts it to the return type required by the proxy method; if incompatible, it can cause `ClassCastException` or `NullPointerException` for a primitive result;
- applies the proxy's exception policy before returning to the caller.

`InvocationHandler.invoke` is declared `throws Throwable`. This **does not mean** every checked exception thrown by the handler will reach the caller intact: the proxy class **enforces the throws restriction** of the interface and may replace the error with an unchecked wrapper.

### 1.1. How are "duplicate" methods understood?

Within the scope of JDK proxy, two interfaces have **duplicate methods in name and parameter signature** when they have the same method name and the same parameter type list in order, including methods inherited from a superinterface.

```java
interface A {
    String find(String key);
}
interface B {
    String find(String key);
}
```

These are two duplicate declarations. Conversely, `find(int)` and `find(String)` are **overloads**, not a pair with duplicate parameter signatures. `throws` is not a component used to distinguish overloads, so:

```java
interface FileService {
    void execute() throws java.io.IOException;
}
interface SqlService {
    void execute() throws java.sql.SQLException;
}
```

The two `execute()` declarations are still duplicate methods, even though `throws` differs. Java allows creating a proxy that implements both if other conditions are valid; **the checked exception restriction occurs when the handler throws an error**, not a rule that "a proxy can only be created if throws are identical".

**Note on return type:** Some interfaces declare the same name/same parameters but different return types in a **covariant** direction (for example `Object` and `String`); a proxy is allowed if the return types are compatible. The JVM method descriptor includes the return type, so separate dispatch/bridge paths may exist. Do not mechanically apply the assumption "always see the same Method even when all return types differ" to the covariant case; section 6 explains this.

## 2. Interface Order Determines the Method Passed to the Handler

Suppose:

```java
interface First {
    String echo(String value) throws java.io.IOException;
}
interface Second {
    String echo(String value) throws Exception;
}
```

When creating:

```java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[]{First.class, Second.class},
        handler);
```

This is an illustrative snippet inside a method that already has `loader` and `handler`. For the `echo(String)` method pair with the same return type, a call to `echo` through **any view** passes to the handler the `Method` object of the interface that **appears earlier in the list** and contains that method.

| Proxy creation interface order | View used to call | Selected `method.getDeclaringClass()` |
| --- | --- | --- |
| `[First, Second]` | `((First) proxy).echo("x")` | `First.class` |
| `[First, Second]` | `((Second) proxy).echo("x")` | `First.class` |
| `[Second, First]` | `((First) proxy).echo("x")` | `Second.class` |
| `[Second, First]` | `((Second) proxy).echo("x")` | `Second.class` |

Why? **A single shared implementation method of the proxy does not know which interface reference the caller held.** The called method has already reached the same implementation of the proxy class; it does not receive a hidden parameter "did the caller cast through First or Second".

This rule is documented in Java SE 17 under **Methods Duplicated in Multiple Proxy Interfaces**. It has two direct consequences:

1. **Do not branch the handler according to caller intent using only `method.getDeclaringClass()`.** With `[First,Second]`, the caller may use `Second`, yet the handler still receives the `Method` declared in `First`.
2. **Interface order is a meaningful part of proxy configuration.** If you change `[First,Second]` to `[Second,First]`, the same call can cause logging, annotation lookup, or routing based on `Method` to change.

### 2.1. Interfaces containing inherited methods

Java considers the earliest interface **that has the method directly or inherited from a parent interface**. For example:

```java
interface Parent {
    String ping();
}
interface Child extends Parent { }
interface Other {
    String ping();
}
```

With the list `[Child.class, Other.class]`, the first interface `Child` **contains** `ping()` via inheritance. The `Method` that the handler sees may have `method.getDeclaringClass() == Parent.class` because the actual declaration is in `Parent`. Therefore:

- "The interface appearing earlier in the array" is different from "the Class returned by `Method.getDeclaringClass()`".
- Do not compare solely `getDeclaringClass() == Child.class` to conclude that the proxy does not handle the `Child` branch.
- If logic per interface contract is needed, attach semantic information when creating the proxy instead of tracing back the caller's reference type from `Method`.

### 2.2. Changing order produces a different proxy class

JDK `Proxy` specifies that two proxy creation requests with the same interfaces but in **different orders** produce **two different proxy classes**. For example, the class for `[First,Second]` is not identical to the class for `[Second,First]`; `proxy.getClass().getInterfaces()` also reflects the order provided.

This is not just a display issue. If code caches proxy classes, stores keys, or builds handlers from the interface array, it must preserve a stable order. Do not treat two interface arrays as "an unordered set".

## 3. Special Exception: Object.equals, hashCode, toString

The three familiar public, non-final methods of `Object` are handled by dynamic proxy as if `Object` stood **before all proxy interfaces** in deciding which `Method` is sent to the handler:

- `boolean equals(Object other)`
- `int hashCode()`
- `String toString()`

Even if a proxy interface redeclares `toString()` with the exact same signature, the handler still receives the `Method` with `getDeclaringClass() == Object.class` for that call.

```java
interface Label {
    String toString();
}
```

This is an illustrative interface. If the handler intends to route using `method.getDeclaringClass() == Label.class`, the `toString` branch will not execute as expected. You should explicitly handle the three `Object` methods, avoiding recursion such as calling `proxy.toString()` inside the handler of `toString` itself.

For example, a handler may choose:
- `equals`: compare identity via `proxy == args[0]` or define appropriate domain value equality;
- `hashCode`: return `System.identityHashCode(proxy)` if using identity;
- `toString`: return a stable proxy description, without calling `proxy.toString()` on itself.

The `equals/hashCode` decisions must be **consistent with each other**. Note that these methods have return types `boolean` and `int` respectively; the handler must return valid `Boolean` and `Integer` wrappers, never `null`.

## 4. The Throws Rule: Intersection at the Checked Exception Level

This is the easiest part to get wrong when combining multiple interfaces.

### 4.1. A single interface

Given:

```java
interface Reader {
    String read() throws java.io.IOException;
}
```

A handler throwing `IOException` matches `throws IOException`; the proxy can propagate `IOException` directly. If the handler throws `SQLException` (checked, not a subtype of `IOException`), the caller will receive `UndeclaredThrowableException` instead of `SQLException` directly.

`RuntimeException` and `Error` are **unchecked**, so they can propagate straight out regardless of whether `throws` declares them.

### 4.2. Multiple interfaces with duplicate methods

Given:

```java
interface Broad {
    void act() throws Exception;
}
interface Narrow {
    void act() throws java.io.IOException;
}
```

A proxy implements both. When the handler throws a **checked Throwable T**, for `T` to reach the caller directly it requires:

> For **each** `act()` method declared or inherited across all relevant proxy interfaces, `T` must be **assignable** to **at least one** exception type in that method's `throws` clause.

In other words, `T` must satisfy **every** throws clause; you cannot look only at the clause of the interface that appears first or only the interface the caller casts to.

For example, in `[Broad,Narrow]`:
- `IOException` and its subclasses: **valid**; `IOException` is both a subtype of `Exception` and in `throws IOException`.
- `SQLException`: **invalid**; it matches `throws Exception` on `Broad` but does not match `throws IOException` on `Narrow`.
- `Exception` (the exact base type): **invalid**; not assignable to `IOException`.
- `IllegalStateException`: is unchecked, so it **is allowed to propagate directly**.

That is the meaning of the proxy's "throws restriction". It does **not** require all interfaces to write the exact same `throws` list, but requires **each specific checked throwable** to be compatible with every relevant declaration.

### 4.3. Two disjoint throws clauses

```java
interface FileAction {
    void save() throws java.io.IOException;
}
interface SqlAction {
    void save() throws java.sql.SQLException;
}
```

A proxy implementing both `FileAction` and `SqlAction` can still be created. However, a handler throwing `IOException` or `SQLException` directly does **not** satisfy both `throws` clauses. A call through **any view** will receive `UndeclaredThrowableException` for that disallowed checked exception.

Changing the order to `[SqlAction,FileAction]` **does not widen** the set of allowed checked exceptions. Order changes the `Method` passed to the handler, but the checked throws restriction is still based on **all duplicate methods**.

### 4.4. One interface declares no throws

If `A.run() throws IOException` but `B.run()` **does not** declare any checked exception, then any checked exception from the handler for that duplicate method pair is disallowed from propagating directly. `RuntimeException` and `Error` can still escape directly.

This can make an API appear to allow I/O failure on one interface, yet a multi-interface proxy wraps the error when another interface without a checked exception declaration is added.

### 4.5. Decision table

| Throws clauses of the duplicate method pair | Handler throws | Proxy call result |
| --- | --- | --- |
| `IOException` and `Exception` | `IOException` | `IOException` directly |
| `Exception` and `IOException` | `SQLException` | `UndeclaredThrowableException` wrapping `SQLException` |
| `IOException` and `SQLException` | `IOException` | `UndeclaredThrowableException` wrapping `IOException` |
| `IOException` and no checked throws | `IOException` | `UndeclaredThrowableException` wrapping `IOException` |
| Any two valid clauses | `IllegalStateException` | `IllegalStateException` directly |
| Any two valid clauses | `AssertionError` | `AssertionError` directly |

**Important:** `Method.getExceptionTypes()` on the **single** `Method` the handler receives only tells you the throws clause of the **selected** method (usually from the earlier interface). It does **not** precompute the intersection of all duplicate methods. With the order `[Broad,Narrow]`, the handler may see `[Exception.class]`, yet `SQLException` is still wrapped by the proxy because `Narrow` only allows `IOException`.

Do not build an error policy by checking **only** `method.getExceptionTypes()` and assuming every checked throwable in that list will be passed straight through by the proxy.

## 5. UndeclaredThrowableException: The Dynamic Proxy Wrapper

`java.lang.reflect.UndeclaredThrowableException` is an **unchecked exception** thrown by the proxy if the handler raises a checked Throwable that is invalid with respect to the declared throws.

```java
try {
    api.save();
} catch (java.lang.reflect.UndeclaredThrowableException wrapper) {
    Throwable original = wrapper.getUndeclaredThrowable();
    // original is the checked Throwable thrown by InvocationHandler.
}
```

This is an illustrative snippet: `api` is a proxy implementing an interface that has `save()`. `getUndeclaredThrowable()` returns the original throwable and can equivalently be read via `getCause()`.

### 5.1. Distinguishing from InvocationTargetException

These two classes have **different origins**:

| Wrapper | Common origin | Which throwable does it contain? |
| --- | --- | --- |
| `InvocationTargetException` | `Method.invoke(...)` in reflection when the target throws an error | The target's actual Throwable, see `getCause()` |
| `UndeclaredThrowableException` | JDK proxy when `InvocationHandler.invoke` throws a checked Throwable **invalid** for the proxy method's throws clauses | The checked Throwable thrown by the handler, see `getUndeclaredThrowable()` |

**Common trap:** a handler using reflection to call a delegate:

```java
InvocationHandler handler = (proxy, method, args) ->
        method.invoke(delegate, args);
```

This is an illustrative snippet with a `delegate` variable and a `Method` that can actually be invoked on the delegate. If the delegate throws `IOException`, then `Method.invoke` creates `InvocationTargetException`. The handler **accidentally throws that checked wrapper** out. If the proxy interface only declares `throws IOException`, it **does not** allow `InvocationTargetException`, so the proxy wraps it **again** in `UndeclaredThrowableException`:

```text
Caller
  -> UndeclaredThrowableException
       -> InvocationTargetException
            -> IOException ("disk")
```

Even though the original `IOException` is in the contract, **the `InvocationTargetException` wrapper** is not in `throws IOException`. Therefore, you must unwrap the reflection layer properly before letting the throwable escape from the handler.

### 5.2. Delegating with reflection properly

```java
InvocationHandler handler = (proxy, method, args) -> {
    try {
        return method.invoke(delegate, args);
    } catch (java.lang.reflect.InvocationTargetException ex) {
        throw ex.getCause();
    }
};
```

This is still an illustrative snippet inside a method that already has a `delegate` compatible with the **declaring class** of `method`. It only solves the wrapper from reflection; it does **not** automatically guarantee the original throwable belongs to the throws clauses of all duplicate interfaces. If the cause is `SQLException` while the method pair has `throws IOException` on one interface, the proxy still wraps it in `UndeclaredThrowableException`.

In particular, when a proxy combines multiple interfaces, the `Method` the handler receives may be a method of an interface **different from the view the caller used**. If the delegate does not implement the interface declared by `method`, `method.invoke(delegate, args)` can fail due to an invalid receiver. Make sure the delegate actually supports that method or resolve the specific target with intentional dispatch.

### 5.3. When handling exceptions at the boundary

In applications, you should:
1. Preserve unchecked exceptions if the contract requires it, and do not swallow `Error`.
2. Only rethrow a checked exception directly when it is valid for **all** duplicate methods.
3. If invalid, convert it into an **unchecked domain exception with a cause**, redesign the interfaces, or split the proxy, instead of relying on an unexpected wrapper.
4. When catching `UndeclaredThrowableException`, inspect `getUndeclaredThrowable()` for diagnosis, but do not arbitrarily unwrap every wrapper layer by default.
5. Preserve the stack trace/cause when translating errors: `new IllegalStateException("Operation failed", original)` is better than copying only the message.

## 6. Compatible Return Types When Interfaces Duplicate a Method

Not every set of interfaces with the same method name and parameters can be combined into a proxy.

### 6.1. Primitive or void return types

If a method in the duplicate set has a **primitive** or `void` return type, all remaining methods must have the **exact same return type**. For example:
- `int number()` and `int number()`: valid.
- `int number()` and `long number()`: **invalid** (even though `int → long` can widen, the proxy does not unify them that way).
- `void run()` and `int run()`: **invalid**.

When calling `Proxy.newProxyInstance` with an incompatible return set, the API throws `IllegalArgumentException` before any proxy object exists.

### 6.2. Reference return types (covariant)

If the return types are all **reference** types, there must exist **one return type** assignable to **all remaining return types** in the set. For example:

```java
interface Wide { Object value(); }
interface Tight { String value(); }
```

`String` is a subtype of `Object`, so a proxy implementing both is allowed. Conversely, `String value()` and `Integer value()` **cannot** both be satisfied by a concrete return type that is a subtype of both final classes, so proxy creation throws `IllegalArgumentException`.

With multiple interfaces having generic erasure or bridge methods, do not infer simply from the printed method name. **The JVM method descriptor also contains the return type**, even though Java source method signatures for overloading do not use the return type. Call sites with covariant returns may go through different entries and create differences in the observed `Method` object. You should not rely on `getDeclaringClass()` to guess the source-interface view in these cases; rely on the formal contract, verify behavior on the target JDK, and keep the dispatcher explicit.

### 6.3. The handler must return a value of the right type

When a proxy method returns `String`, the handler must return a compatible `String` (or `null` if the return is a reference). If it returns `Integer` instead of `String`, the proxy may throw `ClassCastException`.

For a method returning `int`, the handler must return the corresponding wrapper type `Integer`; if it returns `null`, the proxy may throw `NullPointerException` when unboxing. For `void`, the handler's return value does not become a return payload for the caller.

**Fixing the return type by casting inside the handler cannot make a set of interfaces with incompatible return types valid.** The interface set check happens at proxy creation time.

## 7. Complete Java 17+ Example: Order, Throws, Returns, and Wrappers

Save the file **`ProxyDuplicateDemo.java`**. The program uses nested interfaces in a single class so it is easy to run standalone without dependencies outside the JDK.

```java
import java.io.IOException;
import java.sql.SQLException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Arrays;

public class ProxyDuplicateDemo {
    interface Left { String call(String s) throws IOException; }
    interface Right { String call(String s) throws Exception; }
    interface Broad { void act() throws Exception; }
    interface Narrow { void act() throws IOException; }
    interface FileAction { void save() throws IOException; }
    interface SqlAction { void save() throws SQLException; }
    interface Wide { Object value(); }
    interface Tight { String value(); }
    interface InvalidA { String value(); }
    interface InvalidB { Integer value(); }
    interface ObjectLike { String toString(); }
    interface Data { String read() throws IOException; }

    static final class DataImpl implements Data {
        public String read() throws IOException {
            throw new IOException("disk");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ProxyDuplicateDemo.class.getClassLoader();

        InvocationHandler echo = (proxy, method, values) -> {
            System.out.println("selected=" + method.getDeclaringClass().getSimpleName());
            return "ok:" + values[0];
        };
        Object leftFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Left.class, Right.class}, echo);
        System.out.println("asRight=" + ((Right) leftFirst).call("A"));

        Object rightFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Right.class, Left.class}, echo);
        System.out.println("asLeft=" + ((Left) rightFirst).call("B"));
        System.out.println("classesEqual="
                + (leftFirst.getClass() == rightFirst.getClass()));

        Object broadFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Broad.class, Narrow.class},
                (proxy, method, values) -> {
                    System.out.println("methodThrows="
                            + Arrays.toString(method.getExceptionTypes()));
                    throw new SQLException("db");
                });
        try {
            ((Broad) broadFirst).act();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("overlapWrapper="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object compatible = Proxy.newProxyInstance(
                loader, new Class<?>[]{Broad.class, Narrow.class},
                (proxy, method, values) -> { throw new IOException("disk"); });
        try {
            ((Narrow) compatible).act();
        } catch (IOException original) {
            System.out.println("overlapPass=" + original.getClass().getSimpleName());
        }

        Object disjoint = Proxy.newProxyInstance(
                loader, new Class<?>[]{FileAction.class, SqlAction.class},
                (proxy, method, values) -> { throw new IOException("disk"); });
        try {
            ((FileAction) disjoint).save();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("fileView="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }
        try {
            ((SqlAction) disjoint).save();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("sqlView="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object unchecked = Proxy.newProxyInstance(
                loader, new Class<?>[]{FileAction.class, SqlAction.class},
                (proxy, method, values) -> {
                    throw new IllegalStateException("state");
                });
        try {
            ((FileAction) unchecked).save();
        } catch (IllegalStateException original) {
            System.out.println("unchecked="
                    + original.getClass().getSimpleName());
        }

        Object covariance = Proxy.newProxyInstance(
                loader, new Class<?>[]{Wide.class, Tight.class},
                (proxy, method, values) -> "text");
        System.out.println("covariantValue=" + ((Tight) covariance).value());
        try {
            Proxy.newProxyInstance(
                    loader, new Class<?>[]{InvalidA.class, InvalidB.class}, echo);
        } catch (IllegalArgumentException incompatible) {
            System.out.println("badReturns="
                    + incompatible.getClass().getSimpleName());
        }

        Object objectMethod = Proxy.newProxyInstance(
                loader, new Class<?>[]{ObjectLike.class},
                (proxy, method, values) -> {
                    System.out.println("objectDeclaring="
                            + method.getDeclaringClass().getSimpleName());
                    return "proxy-text";
                });
        System.out.println("objectResult=" + objectMethod.toString());

        DataImpl target = new DataImpl();
        Data raw = (Data) Proxy.newProxyInstance(
                loader, new Class<?>[]{Data.class},
                (proxy, method, values) -> method.invoke(target, values));
        try {
            raw.read();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("rawForwarding="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Data unwrapped = (Data) Proxy.newProxyInstance(
                loader, new Class<?>[]{Data.class},
                (proxy, method, values) -> {
                    try {
                        return method.invoke(target, values);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
        try {
            unwrapped.read();
        } catch (IOException original) {
            System.out.println("unwrapped=" + original.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 ProxyDuplicateDemo.java
java ProxyDuplicateDemo
```

**Verified stdout:**

```text
selected=Left
asRight=ok:A
selected=Right
asLeft=ok:B
classesEqual=false
methodThrows=[class java.lang.Exception]
overlapWrapper=SQLException
overlapPass=IOException
fileView=IOException
sqlView=IOException
unchecked=IllegalStateException
covariantValue=text
badReturns=IllegalArgumentException
objectDeclaring=Object
objectResult=proxy-text
rawForwarding=InvocationTargetException
unwrapped=IOException
```

### 7.1. Why did the handler select Left when the caller called via Right?

The first proxy was created with order `[Left,Right]`. Even though the caller cast to `Right` and called `call("A")`, the handler still received the `Method` declared in `Left`. The second proxy reverses the order `[Right,Left]`, so the handler receives `Right` even though the caller cast to `Left`. `classesEqual=false` shows that order also distinguishes proxy classes.

### 7.2. Why was `SQLException` wrapped even though Method reported `throws Exception`?

The `broadFirst` proxy has `[Broad,Narrow]`. The `Method` the handler receives comes from `Broad`, so `method.getExceptionTypes()` prints `[class java.lang.Exception]`. However, the duplicate method on `Narrow` only declares `throws IOException`. `SQLException` is not a subtype of `IOException`, so the proxy throws `UndeclaredThrowableException`; the program unwraps it and prints `overlapWrapper=SQLException`.

This is practical proof that **reading only the metadata of the first Method is not enough to conclude the valid set of checked exceptions**.

### 7.3. The case where the throws intersection accepts IOException

The `compatible` proxy also implements `[Broad,Narrow]`, but the handler throws `IOException`. It is compatible with both `throws Exception` and `throws IOException`, so the caller `((Narrow) compatible).act()` catches `IOException` directly.

### 7.4. The case where two throws have no valid intersection

`disjoint` combines `FileAction.save() throws IOException` and `SqlAction.save() throws SQLException`. A handler throws `IOException`, and the proxy wraps it in `UndeclaredThrowableException` regardless of whether the caller uses `FileAction` or `SqlAction`. The two lines `fileView=IOException` and `sqlView=IOException` record the **original** retrieved from the wrapper, not the outer-level exception class.

### 7.5. Unchecked exceptions and Object methods

`IllegalStateException` is unchecked, so the proxy does not subject it to the throws intersection. `ObjectLike.toString()` is selected as a method of `Object`, hence it prints `objectDeclaring=Object`.

### 7.6. Return type compatibility and limits at proxy creation time

`Wide.value(): Object` and `Tight.value(): String` have compatible returns; the proxy is created and returns `"text"`. `InvalidA.value(): String` and `InvalidB.value(): Integer` have incompatible reference returns, so `Proxy.newProxyInstance` throws `IllegalArgumentException`. This is a **proxy creation** error, not a checked exception of the target.

### 7.7. Why does wrong reflection forwarding cause double wrapping?

`Data.read() throws IOException` is a valid contract for target `DataImpl`. When the handler writes `method.invoke(target, values)`, `Method.invoke` creates **`InvocationTargetException`**; that checked wrapper is not in `throws IOException`, so the proxy adds **`UndeclaredThrowableException`**. The line `rawForwarding=InvocationTargetException` shows that the throwable inside the proxy wrapper is the reflection wrapper. The `unwrapped` version catches `InvocationTargetException` and throws the cause, so `IOException` propagates directly per the contract and prints `unwrapped=IOException`.

## 8. Designing a Safe Handler for Multiple Interfaces

### 8.1. Do not use declaring class as "caller identity"

This is an anti-pattern:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getDeclaringClass() == First.class) {
        return callFirstBusinessLogic(args);
    }
    if (method.getDeclaringClass() == Second.class) {
        return callSecondBusinessLogic(args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

This is an **illustrative counterexample**; `callFirstBusinessLogic` and `callSecondBusinessLogic` represent business logic, not built-in methods. With duplicate signatures and `[First,Second]`, the `Second` branch may **never run for `echo(String)`**, even if the caller casts to `Second`.

A proxy cannot know "which reference type the caller wanted to use" solely from the `Method` of a duplicate signature. If two interfaces define **different semantics** for the same name/parameters, avoid combining both into one proxy with the same dispatcher or introduce a clearer API.

### 8.2. More reliable design options

- **Unify the contract:** If two interfaces have duplicate methods with the same semantics, write one shared handling branch. Check the throws intersection and return types during design.
- **Split the proxy:** If the signature is duplicated but the semantics differ, use **two proxy objects** or two adapters with separate contexts. The caller knows which object performs which business logic.
- **Dispatch by signature and configuration:** Create a key consisting of name + parameter types (and return descriptor if truly needed), bound in advance to an explicit target handler. Do not use `Method` identity or an interface name inferred from the caller's cast.
- **Provide an explicit operation identifier:** If the app needs to distinguish two behaviors, give the methods different names or pass operation info in arguments, instead of expecting the proxy to guess from the reference.
- **Build an error policy at the boundary:** Check all duplicate declarations before letting a checked exception escape; for errors that cannot be represented in the contract, use an unchecked domain exception with a cause or redesign the interfaces.

### 8.3. Attaching metadata when creating a proxy

A large system can pre-build a descriptor for each method group:
- method name and parameter types;
- list of interfaces that declare/inherit that method;
- valid return types;
- set of checked exceptions allowed to pass through all declarations;
- dispatcher target, security checks, and exception translation policy.

This can be done at **proxy creation time** rather than on every call. It helps detect conflicts early and avoid unnecessary repeated reflection. However, a descriptor still cannot make two different semantics distinguishable solely by the caller's cast.

### 8.4. Interface order and annotations

If two interfaces have different annotations on a duplicate method, the `Method` passed to the handler follows the interface order in the case of the same descriptor. Therefore, a handler reading `method.getAnnotation(...)` may observe **different metadata when the order changes**, even if the caller keeps the same interface view.

Do not treat reading annotations on that single `Method` as sufficient if you need to aggregate policies from **all interfaces**. Resolve all declarations during proxy initialization, apply a well-defined conflict rule, and test the reversed order.

### 8.5. Default methods and interface order

Dynamic proxy also forwards interface method calls into the handler. Java 17 supports `InvocationHandler.invokeDefault(proxy, method, args)` so the handler can **actively** invoke an appropriate default method. If multiple interfaces have competing default methods, do not assume that changing interface order will automatically select the desired "business implementation". You must explicitly select a valid default method according to the API contract.

The rule for selecting `Method` for duplicate methods, choosing the **target** to delegate to, and checking throws are three separate responsibilities.

## 9. Other Constraints of Proxy.newProxyInstance

When combining interfaces, besides return compatibility and throws, you also need to check:

1. Each element of `interfaces` is actually a suitable **interface type**; Java 17 does not accept classes, primitives, hidden, or sealed interfaces as proxy interfaces per the API conditions.
2. You must not repeat **the exact same Class object** in the `interfaces` array; however, you can combine multiple **different** interfaces that have duplicate methods.
3. All interfaces must be **visible to the specified class loader** with exact identity; using the wrong class loader can cause proxy creation to fail.
4. For **non-public interfaces**, the same-package/module conditions and related accessibility rules must be satisfied. Just having a `Class<?>` does not guarantee a proxy can always be created.
5. Return types of duplicate methods must be compatible. Otherwise, `Proxy.newProxyInstance` throws `IllegalArgumentException`.
6. The interface list and generated proxy class must stay within JVM limits; do not build arbitrary lists from unvalidated input.

Java SE 17 documentation also describes the package/module location of the proxy class in JPMS. When encountering encapsulation errors, distinguish **module/loader configuration errors** from **throws restrictions in the handler**; they occur at different phases.

## 10. Matrix-Based Testing and Debugging

A test suite for a proxy combining multiple interfaces should include:

| Test group | Condition | Expected outcome to verify |
| --- | --- | --- |
| Interface order | `[A,B]` and `[B,A]` with duplicate method of same return | Selected `Method` changes; two different proxy classes |
| Reference view | Call one proxy via `A` and `B` | With the same duplicate descriptor, declared method is determined by interface order, not by cast |
| Inheritance | First interface inherits method from parent | `Method.getDeclaringClass()` may be parent |
| Object methods | Interface redeclares `toString()` | `Method.getDeclaringClass() == Object.class` |
| Overlapping checked throws | `throws Exception` and `throws IOException`, handler throws `IOException` | `IOException` directly |
| Incompatible checked throws | Above pair, handler throws `SQLException` | `UndeclaredThrowableException` wrapping `SQLException` |
| Two disjoint throws | `IOException` and `SQLException` | Neither `IOException` nor `SQLException` allowed directly |
| One declaration with no throws | One interface declares no checked throws | Checked from handler is wrapped |
| Unchecked | Handler throws `IllegalStateException` | Escapes directly |
| Covariant returns | `Object` and `String` | Proxy can be created, returns compatible value |
| Return conflict | `String` and `Integer` or `int` with `long` | Proxy creation rejected with `IllegalArgumentException` |
| Wrong result from handler | Method returns `String`, handler returns `Integer` | `ClassCastException` at proxy boundary |
| Reflection delegate | Handler rethrows `InvocationTargetException` without unwrapping | May become double wrapper; proper handling must throw valid cause |

**Note when measuring/comparing:** do not use `Method.toString()` as a unique ID for routing. Display names, generic erasure, inheritance, return covariance, and class loaders can skew analysis. Use structured metadata and check in the proper context.

## 11. Common Misconceptions

1. **“Whichever interface the caller casts to, the handler receives that interface's Method.”** False for duplicate methods with the same descriptor: the earlier interface in the list decides.
2. **“Two interfaces with different throws cannot form a proxy.”** False. The throws restriction is enforced when the handler throws a checked throwable.
3. **“The handler is declared throws Throwable so the proxy does not check.”** False. A checked Throwable must still be compatible with all duplicate methods.
4. **“Method.getExceptionTypes() in the handler is the list of allowed checked throwables.”** Insufficient: it only reflects the single selected Method, not the intersection of multiple interfaces.
5. **“A caller using FileAction can receive IOException directly, even if the proxy also implements SqlAction with an identical save().”** False if that checked throwable is not compatible with `SqlAction.save()`.
6. **“UndeclaredThrowableException and InvocationTargetException are the same.”** False: they belong to two different boundaries and can be nested.
7. **“Just changing interface order fixes a checked exception mismatch.”** False. It only changes the selected Method; it does not change the contract of all methods.
8. **“Changing return from int to long is fine because of primitive widening.”** False. Proxy requires exact matching for primitive/void returns.
9. **“Use Method.getDeclaringClass() to distinguish semantics when two interfaces share a method.”** You cannot reliably infer the caller view that way.
10. **“The proxy automatically calls the default method instead of entering the handler.”** Do not rely on this assumption. The handler must handle/default-dispatch per the API.
11. **“Method.invoke(delegate, args) is always the right forwarding.”** Not if the delegate does not implement the declaring interface, or when a checked reflection wrapper is not unwrapped.
12. **“Declaring no checked exceptions means every throwable will be wrapped.”** False. `RuntimeException` and `Error` are unchecked and are not restricted that way.

## 12. Self-Check Exercises

### Exercise 1 — Order and view

Given:

```java
interface A { String name(); }
interface B { String name(); }
```

The proxy is created with `[B.class,A.class]`. The caller uses `((A)p).name()`. In the case where both methods have the same return descriptor, which class is `method.getDeclaringClass()` in the handler?

**Answer:** `B.class`. The reference view `A` does not determine the Method sent to the handler.

### Exercise 2 — Checked exceptions intersection

Given:
- `A.run() throws Exception`;
- `B.run() throws IOException`;
- `C.run() throws FileNotFoundException`.

If the handler throws `IOException`, can it propagate directly when the proxy implements all three? What if the handler throws `FileNotFoundException`?

**Answer:** A plain `IOException` cannot, because it is not assignable to `C`'s `FileNotFoundException`; an actual instance of `FileNotFoundException` is allowed because it is a subtype of all three exception types.

### Exercise 3 — Disjoint

A proxy implements `X.send() throws IOException` and `Y.send() throws SQLException`. The handler throws `IOException`. Is there any difference if the caller casts the proxy to `X` or `Y`?

**Answer:** No. Checked `IOException` does not satisfy `Y`, so the proxy wraps it in `UndeclaredThrowableException` under both views.

### Exercise 4 — Double wrapper

The handler calls `method.invoke(delegate,args)`, the delegate throws `IOException`, and the interface only declares `throws IOException`. Why does the caller see `UndeclaredThrowableException` instead of `IOException`?

**Answer:** `Method.invoke` wrapped the cause in the checked `InvocationTargetException`; the handler threw that wrapper itself. `InvocationTargetException` is not a subtype of `IOException`, so the proxy created an unchecked wrapper. You must catch `InvocationTargetException` and rethrow `getCause()`.

### Exercise 5 — Return type

Can you create a proxy combining:
- `Object item()` with `String item()`?
- `Number item()` with `Integer item()`?
- `int count()` with `long count()`?
- `String item()` with `Integer item()`?

**Answer:** The first two pairs are valid because a compatible reference return subtype exists (`String` and `Integer`). The last two pairs are invalid: primitives must match exactly; `String` and `Integer` are two reference types with no common return subtype satisfying both final classes.

### Exercise 6 — Designing the right contract

Two interfaces both declare `void submit(String id)`, but one interface means "payment" and the other means "confirm shipment". Should you combine them into one proxy and use the caller's cast to distinguish them inside the handler?

**Answer:** No. The same duplicate signature does not carry caller reference view information into the handler. Use two proxy objects, two differently named methods, or pass an explicit operation so semantics are not mixed.

## Official Documentation

- [Java SE 17 — Proxy, Methods Duplicated in Multiple Proxy Interfaces section](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): Method selection by interface order, Object methods, checked throws, and return type rules.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invoke` contract, return values, and throwable restrictions.
- [Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): wrapper for checked exceptions not permitted by the interface.
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper from `Method.invoke` when the target throws a throwable.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getDeclaringClass`, `getExceptionTypes`, and `invoke`.

## Conclusion

When a JDK dynamic proxy implements multiple interfaces containing the same method name and the same parameter signature, **interface order determines the Method dispatched for that duplicate signature**, not the reference type used by the caller. However, **throws is not determined by that Method alone**: for a checked throwable to escape directly, it must be compatible with **all throws clauses** of the duplicate methods; otherwise, the proxy throws `UndeclaredThrowableException`. For return types, the proxy can only be created if the declarations are compatible; `Object` methods and covariance also have special rules. Build handlers around an **explicit shared contract**, check the exception policy before delegating, properly unwrap `InvocationTargetException` when using reflection, and split proxies if two interfaces share a signature but have different semantics.
