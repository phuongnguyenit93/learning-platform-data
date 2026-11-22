# 10.9. Calling Default Methods via `InvocationHandler.invokeDefault`

Java dynamic proxy creates an object implementing one or more interfaces at runtime and dispatches method calls to an `InvocationHandler`. A common misconception is that **a `default` method in an interface automatically runs its default body when called on a dynamic proxy**: the call still goes through the handler. If you want to execute the actual `default` body, starting from Java 16 you can use the standard API:

```java
InvocationHandler.invokeDefault(proxy, method, args);
```

This is a **`static`** method of `java.lang.reflect.InvocationHandler`, not a method of the handler object. It performs a special invocation to the `default` body of the interface, semantically equivalent to a valid `InterfaceName.super.method(...)` call from the proxy class. This article explains the mechanism, validity conditions for `Method`, parameter handling, multiple inheritance/same-named default methods, exceptions, and a complete Java 17+ example.

## 1. Why Does a Dynamic Proxy Need `invokeDefault`?

In a normal class, an interface can provide default behavior:

```java
interface Greeting {
    String prefix(String name);

    default String greet(String name) {
        return prefix(name) + name;
    }
}
```

A class implementing `Greeting` directly can inherit `greet` and use that default body. However, with a dynamic proxy:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

**Every call through the proxy's interface**, including `greet` which is default, is forwarded to:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

`Proxy` provides the mechanism to dispatch to the handler; it does not by default decide that when `method.isDefault() == true` it should run the interface's code. The handler must choose a behavior:

- Return a result computed by the handler itself.
- Delegate to a real target service/object.
- **Run the default body** with `InvocationHandler.invokeDefault(...)`.
- Reject the call with an intentional exception.

For example, the default method `greet` calls `prefix(name)`; when `greet` is executed on the proxy, the `prefix` call inside the default body **still goes through the handler**, because `this` of the default body is the proxy. This is a design benefit: a default method can coordinate abstract/interface calls provided by the handler.

**Key point:** `invokeDefault` bypasses the handler's dispatch **for the selected default body call itself**. It does not turn every call inside the default body into a direct call: subsequent virtual/interface calls on the proxy can still go back to the handler.

## 2. API, Java Version, and Signature

In Java SE 17, the API has the signature:

```java
public static Object invokeDefault(
        Object proxy, Method method, Object... args)
        throws Throwable;
```

Meaning of each parameter:

| Parameter | Meaning | Constraints |
| --- | --- | --- |
| `proxy` | **The dynamic proxy object** that will act as `this` of the default method | Must be a proxy instance created by `java.lang.reflect.Proxy`; `null` or a regular object is not accepted |
| `method` | Metadata of the default method to execute | Must be a valid default method declared in a proxy interface or validly inherited from a superinterface, not overridden in a way that makes the target unresolvable |
| `args` | The actual arguments passed to the default method | Count and types must be compatible with the formal parameters; `null` may be passed if the method takes no parameters |

The `Object` return type is the return value of the default method (primitives are boxed when needed; a `void` default method has no useful result). The default body may throw errors; the API declares `throws Throwable` to propagate exceptions from the target code.

**Availability:** `InvocationHandler.invokeDefault` was added in **Java 16**. The examples in this article are compiled with `javac --release 17`. If a project targets Java 8/11 API level, this new method cannot be called directly; you need to reconsider the minimum runtime version or use a different compatibility strategy. Do not assume that using reflection to bypass compile-time checks will make the API exist in an older JDK.

Minimal example at the handler position:

```java
InvocationHandler handler = (proxy, method, arguments) -> {
    if (method.isDefault()) {
        return InvocationHandler.invokeDefault(proxy, method, arguments);
    }
    // Handle calls without a default body according to the application contract.
    throw new UnsupportedOperationException(method.getName());
};
```

The snippet above **only illustrates the `default` branch**; the rest of the handler needs to handle abstract methods and `Object` methods appropriately. The standalone runnable example in section 7 includes those branches.

## 3. Dispatch Flow: From Proxy to the `default` Body

Logical diagram for `greeting.greet("Lan")`:

```text
Caller -> proxy.greet("Lan")
          |
          v
 InvocationHandler.invoke(proxy, method=greet, args=["Lan"])
          |
          +-- method.isDefault() == true
          |
          v
 InvocationHandler.invokeDefault(proxy, method, args)
          |
          v
 Execute the body of Greeting.default greet("Lan")
          |
          +-- default body calls prefix("Lan") on this = proxy
                         |
                         v
              InvocationHandler.invoke(..., method=prefix, ...)
                         |
                         v
              Handler returns prefix, e.g. "Hi, "
          |
          v
 Default method returns "Hi, Lan"
          |
          v
 Handler returns the result to the caller
```

`invokeDefault` works equivalently to an `invokespecial` instruction targeting **the selected interface's default body**. This differs from `Method.invoke(proxy, arguments)`:

- `InvocationHandler.invokeDefault(proxy, method, args)` selects the exact default body and does not dispatch that same call back to the handler.
- `method.invoke(proxy, args)` is a normal reflective call on the proxy; it can **dispatch back to the handler itself**. Calling it inside the branch handling the same method easily creates an infinite recursive loop and `StackOverflowError`.
- `method.invoke(realTarget, args)` can be valid if the application is delegating to a **real object** implementing the interface; that is a different mechanism, not equivalent to invoking the default body on the proxy itself.

**Do not** use `method.invoke(proxy, args)` as a substitute for `invokeDefault` inside a handler to "call the default implementation".

## 4. Passing the Right `Method`: `isDefault` Is Not Enough

`Method.isDefault()` indicates whether a `Method` is an interface default method (as opposed to an abstract, static, or private interface method). It is useful for branching, but **does not prove that the method is valid for a specific proxy**.

For `invokeDefault(proxy, method, args)` to be valid, the method must be a default method that the proxy interface directly or indirectly **can invoke under default method resolution rules**. In other words, the behavior must be equivalent to a valid `X.super.m(...)` call from the proxy class.

Therefore:

1. A `default` method declared directly in an interface that the proxy implements can be a target.
2. A `default` method **inherited** from a superinterface (and not overridden in a way that loses resolution to that body) can also be a target.
3. A `default` method in an interface **unrelated** to the proxy is an **invalid** target, even if `method.isDefault()` returns `true`.
4. If a proxy interface **overrides** a superinterface's default body, attempting to invoke the old `Method` of the superinterface may be rejected, because it is no longer a method that an `X.super.m` call can resolve to.
5. An **abstract** or `static` method does not become a default method merely by sharing a name/signature with another method.

For example, given:

```java
interface Base {
    default String source() { return "base"; }
}
interface Inherited extends Base {}
interface Overridden extends Base {
    @Override
    default String source() { return "overridden"; }
}
```

A proxy implementing only `Inherited` can call the `Base.source` body because `Inherited` inherits that default. A proxy implementing only `Overridden` can call `Overridden.source`, but must not try to call `Base.source` via `invokeDefault` as if the overriding version did not exist.

**Consequence when upgrading libraries:** A handler that caches `Base.class.getMethod("source")` and uses it across all versions of `Derived` can break after `Derived` adds an override of `source`. It is not merely a change in return value; calling `invokeDefault` on the old method can throw `IllegalArgumentException`. You should check the version/interface graph and avoid assuming that every default method in an ancestor remains valid forever.

## 5. Two Interfaces with the Same Default Method: Choosing an Implementation Intentionally

Suppose:

```java
interface Left {
    default String label() { return "left"; }
}
interface Right {
    default String label() { return "right"; }
}
```

A regular class cannot implement two defaults with the same signature without resolving the conflict. A dynamic proxy can implement both `Left` and `Right`, because methods on the proxy are dispatched to the handler, and the handler can choose which default body to run using `invokeDefault`.

Important point: when a proxy is created from the list:

```java
new Class<?>[]{Left.class, Right.class}
```

a call to `label()` may pass into the handler the `Method` object belonging to **the interface that appears first in the list** (here `Left`), even when the caller invokes it through a `Right` variable. The proxy does not know which static interface reference the caller used when deciding among methods with the same signature.

Therefore, handler code like the following might **not** select the default body the user expects:

```java
// method may be Left.label() for both reference types.
return InvocationHandler.invokeDefault(proxy, method, args);
```

If the application contract chooses **Right** for both call paths, explicitly select `Right.class.getMethod("label")`:

```java
InvocationHandler chooseRight = (proxy, method, args) -> {
    Method rightMethod = Right.class.getMethod("label");
    return InvocationHandler.invokeDefault(proxy, rightMethod, args);
};
```

This snippet is only valid when the handler is attached to a proxy implementing both `Left` and `Right`, and is handling a `label` call; in real code you must branch by name/signature rather than mapping every `Method` to a single default method. The complete program below creates the proxy in the proper context and shows that both `((Left) proxy).label()` and `((Right) proxy).label()` can return `"right"`.

**Do not confuse this with the `Method` passed to the handler:** It is metadata describing the method dispatched by the proxy, not something that must be passed verbatim into `invokeDefault`. When choosing a different method, you must ensure that method still belongs to the valid default targets of the proxy.

## 6. Parameters, `null`, Primitives, and Varargs

### 6.1. The Handler's `Object[] args` Array

`InvocationHandler.invoke(proxy, method, args)` receives an `Object[]` containing arguments with primitives boxed. For a method with **no parameters**, the JVM may pass `args == null`. `invokeDefault` also accepts `args == null` when the target method has **0 parameters**.

Natural forwarding:

```java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

This syntax passes `args` of type `Object[]` to the `Object...` varargs parameter of `invokeDefault`, thereby passing **the elements of the array** as arguments to the default method. If the handler receives `args == null` when the method has no parameters, the call is still valid. You may normalize with `args == null ? new Object[0] : args` if the application needs a non-null array for its own processing, but it is not required to invoke a 0-parameter default method.

### 6.2. Argument Count and Unboxing Must Match

Given:

```java
interface NumberOps {
    default int twice(int n) { return n * 2; }
}
```

Suppose `numberProxy` has already been created to implement `NumberOps` and `twice` is `NumberOps.class.getMethod("twice", int.class)`:

```java
Object ok = InvocationHandler.invokeDefault(
        numberProxy, twice, 6);              // Integer(12)
Object bad = InvocationHandler.invokeDefault(
        numberProxy, twice, (Object) null);  // IllegalArgumentException
```

This snippet is illustrative; the variables `numberProxy`/`twice` must be created beforehand. The primitive `int` is boxed into `Integer` across the Object/varargs boundary and unboxed when executing the default method. `null` cannot be unboxed to `int`. `invokeDefault` can throw **`IllegalArgumentException`** if the number or types of arguments do not match, including failed unboxing as in this case. This is an **input argument** error, not an exception thrown by the `twice` body itself.

### 6.3. When the Target Method Itself Takes an Array

For example, a default method taking a `String[]` parameter:

```java
interface Tags {
    default int count(String[] tags) { return tags.length; }
}
```

If calling `invokeDefault` from outside a handler and you want to pass the array as **a single argument**, prevent Java from spreading the array elements across `Object...`:

```java
// Assume tagProxy implements Tags and countMethod is Tags.count(String[]).
int n = (int) InvocationHandler.invokeDefault(
        tagProxy, countMethod, (Object) new String[]{"a", "b"});
```

The `(Object)` cast forces the `String[]` array to be passed as **a single element** of the varargs; do not confuse the parameter count of `count(String[])` with the length of `tags`. If receiving a normal call `tagsProxy.count(array)` inside a handler, `args` already contains **one element which is the `String[]` array**; forwarding `args` directly to `invokeDefault` is correct.

Do not cast or wrap the array arbitrarily: `invokeDefault(proxy, method, new Object[]{args})` would pass the entire `Object[] args` as *one* parameter, which is usually wrong for methods with multiple parameters.

## 7. Complete Java 17+ Example: Default, Inheritance, Duplicate Methods, Override, and Errors

Save the **entire** program below as `ProxyDefaultMethodsDemo.java`. The interfaces are declared `public` nested inside a public class to avoid external package dependencies; the program uses only standard `java.base` APIs. When compiling, the JVM will generate extra `.class` files for the nested interfaces as usual.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyDefaultMethodsDemo {
    public interface Greeter {
        String prefix(String name);
        default String greet(String name) { return prefix(name) + name; }
        default String signature() { return "from-Greeter"; }
        default int doubleNumber(int n) { return n * 2; }
    }

    public interface Left {
        default String label() { return "left"; }
    }

    public interface Right {
        default String label() { return "right"; }
    }

    public interface Base {
        default String source() { return "base"; }
    }

    public interface Inherited extends Base {}

    public interface Overridden extends Base {
        @Override
        default String source() { return "overridden"; }
    }

    public interface Failure {
        default void crash() {
            throw new IllegalStateException("from-default");
        }
    }

    public static void main(String[] args) throws Throwable {
        InvocationHandler greeterHandler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreeterProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }
            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, arguments);
            }
            if (method.getName().equals("prefix")) {
                return "Hi, ";
            }
            throw new UnsupportedOperationException(method.getName());
        };

        Greeter g = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] {Greeter.class}, greeterHandler);

        System.out.println("greet=" + g.greet("Lan"));
        System.out.println("signature=" + g.signature());
        System.out.println("toString=" + g);
        System.out.println("double=" + g.doubleNumber(4));

        Method greetMethod = Greeter.class.getMethod("greet", String.class);
        System.out.println("isDefault=" + greetMethod.isDefault());
        System.out.println("direct=" +
                InvocationHandler.invokeDefault(g, greetMethod, "Mai"));

        Method twice = Greeter.class.getMethod("doubleNumber", int.class);
        System.out.println("directDouble=" +
                InvocationHandler.invokeDefault(g, twice, 6));

        InvocationHandler chooseRight = (proxy, method, arguments) -> {
            Method right = Right.class.getMethod("label");
            return InvocationHandler.invokeDefault(proxy, right, arguments);
        };
        Left both = (Left) Proxy.newProxyInstance(
                Left.class.getClassLoader(),
                new Class<?>[] {Left.class, Right.class}, chooseRight);

        System.out.println("twoDefaults.left=" + both.label());
        System.out.println("twoDefaults.right=" + ((Right) both).label());

        Inherited inherited = (Inherited) Proxy.newProxyInstance(
                Inherited.class.getClassLoader(),
                new Class<?>[] {Inherited.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        System.out.println("inherited=" + inherited.source());

        Overridden overridden = (Overridden) Proxy.newProxyInstance(
                Overridden.class.getClassLoader(),
                new Class<?>[] {Overridden.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        System.out.println("overridden=" + overridden.source());

        try {
            Method obsolete = Base.class.getMethod("source");
            InvocationHandler.invokeDefault(overridden, obsolete);
        } catch (IllegalArgumentException e) {
            System.out.println("overridden.base="
                    + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(g, greetMethod);
        } catch (IllegalArgumentException e) {
            System.out.println("badArity=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(g, twice, (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println("badPrimitive=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(
                    g, Greeter.class.getMethod("prefix", String.class), "A");
        } catch (IllegalArgumentException e) {
            System.out.println("notDefault=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(
                    new Object(), greetMethod, "Hoa");
        } catch (IllegalArgumentException e) {
            System.out.println("notProxy=" + e.getClass().getSimpleName());
        }

        Failure failure = (Failure) Proxy.newProxyInstance(
                Failure.class.getClassLoader(),
                new Class<?>[] {Failure.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        try {
            failure.crash();
        } catch (IllegalStateException e) {
            System.out.println("targetException="
                    + e.getClass().getSimpleName() + ":" + e.getMessage());
        }
    }
}
```

Open a terminal in the directory containing the file and run:

```bash
javac --release 17 ProxyDefaultMethodsDemo.java
java ProxyDefaultMethodsDemo
```

Exact **`stdout`** output of the program:

```text
greet=Hi, Lan
signature=from-Greeter
toString=GreeterProxy
double=8
isDefault=true
direct=Hi, Mai
directDouble=12
twoDefaults.left=right
twoDefaults.right=right
inherited=base
overridden=overridden
overridden.base=IllegalArgumentException
badArity=IllegalArgumentException
badPrimitive=IllegalArgumentException
notDefault=IllegalArgumentException
notProxy=IllegalArgumentException
targetException=IllegalStateException:from-default
```

### 7.1. Explaining Key Points

**`greet=Hi, Lan`:** the handler receives `Greeter.greet` as a default method and uses `invokeDefault` to run its default body; inside, `prefix("Lan")` calls back into the proxy so the handler receives `prefix` and returns `"Hi, "`. This is **intentional re-entry**, not a recursive loop back into the same `greet` method.

**`signature=from-Greeter`:** `signature` has no parameters; in the handler, the `arguments` array may be `null`. `invokeDefault(proxy, method, arguments)` validly handles the 0-parameter case. **`toString=GreeterProxy`**: `Object.toString` is not an interface default method, so the handler handles it separately.

**`double=8` and `directDouble=12`:** the default method returns primitive `int`; the handler returns the value as `Object`, and the application receives the proper primitive through the proxy's boxing/unboxing mechanism. A direct call to `invokeDefault` returns an `Integer` in the `Object` return position.

**`twoDefaults.left=right` and `twoDefaults.right=right`:** the proxy implements both `Left` and `Right`, but the handler intentionally selects `Right.label`. Choosing the implementation is **the handler's policy**, not determined automatically by the caller expression's static type `Left`/`Right`.

**`inherited=base`:** the proxy implements `Inherited`, and `Inherited` validly inherits the default method `Base.source`, so the `Base` body can be invoked.

**`overridden=overridden` / `overridden.base=IllegalArgumentException`:** once `Overridden` overrides `Base.source`, the default-invocable method is `Overridden.source`; trying to force `Base.source` via `invokeDefault` on a proxy implementing only `Overridden` is rejected.

**`badArity`, `badPrimitive`, `notDefault`, `notProxy`:** test wrong argument count, `null` for `int`, selecting an abstract non-default method, and a non-dynamic-proxy object respectively.

**`targetException=IllegalStateException:from-default`:** the exception thrown by **the default body itself** is propagated to the handler/caller, and is not wrapped in `InvocationTargetException` by `invokeDefault`.

## 8. Exceptions and Errors: Distinguishing Where They Originate

### 8.1. `invokeDefault` Call Preparation Errors

| Exception | Typical Condition | How to Handle |
| --- | --- | --- |
| `NullPointerException` | `proxy == null` or `method == null` | Check references before calling |
| `IllegalArgumentException` | `proxy` is not a dynamic proxy, or `Method` is not a valid default target or does not belong to the proxy's interfaces | Check proxy interfaces, `method.isDefault()`, declaring class, and override chain |
| `IllegalArgumentException` | Wrong argument count/types, unable to unbox primitive, or value is not assignable to parameter | Compare `method.getParameterTypes()` and the argument array |
| `IllegalAccessException` | Declaring class of the default method is not accessible from the caller | Check visibility, package/module, and public API |
| `Throwable` thrown by default body | Execution entered the default body and then failed | Handle business exceptions; do not automatically blame the reflection signature |

`NoSuchMethodException` can come from **looking up the Method** via `Interface.class.getMethod(...)`; it is not an exception of `invokeDefault` itself once you have the right `Method`.

**Note:** For a `void` default method, `invokeDefault` returns `Object` with no business value to use. For a default method returning a primitive, the result is boxed to satisfy the `Object` return type. When a handler returns `null` for an interface method with a primitive return type, calling through the proxy can throw `NullPointerException` due to unboxing at the proxy boundary; that is not a normal way to represent `0`/`false`.

### 8.2. Errors from the Default Body Do Not Automatically Become `InvocationTargetException`

Two similarly named APIs have different semantics:

```java
// Invoke default body via special invocation:
InvocationHandler.invokeDefault(proxy, defaultMethod, args);

// Reflective call Method.invoke via normal dispatch:
defaultMethod.invoke(proxy, args);
```

`Method.invoke` uses normal reflection and wraps exceptions thrown by the target in `InvocationTargetException`; when the receiver is a proxy, the dispatch target is the method on the proxy and may go back to the handler. `InvocationHandler.invokeDefault` is a way to invoke **the default body** and propagates `Throwable` from that body according to its contract. Do not catch `InvocationTargetException` from `invokeDefault` as if it were always a wrapper created by this API.

If a default method throws `IllegalStateException` directly, the handler calling `invokeDefault` can receive that exception directly. If the handler lets an **undeclared checked exception** escape from `InvocationHandler.invoke`, the call through the proxy may wrap the checked exception in `UndeclaredThrowableException` per dynamic proxy rules. This is **a check at the proxy method boundary**, not `InvocationTargetException` wrapping by `invokeDefault`.

In real systems, there should be a clear exception policy: preserve checked exceptions declared by the interface; log/provide context for business errors; preserve cause and stack trace; avoid catching all `Throwable` and silently returning `null`.

## 9. Visibility, Modules, and Interface Changes Over Time

`InvocationHandler.invokeDefault` can only invoke methods that comply with access rules. If the declaring class is not accessible from the caller, the API can throw **`IllegalAccessException`**. Successfully creating a dynamic proxy does not necessarily guarantee that **every default method arbitrarily retrieved by code** can be invoked from every module.

With the Java Platform Module System (JPMS):

- Interfaces must be visible/eligible to create a proxy under `Proxy.newProxyInstance` rules.
- The default method must be valid and the declaring interface must be accessible in the caller's context.
- Do not default to using `setAccessible(true)` or `--add-opens` as a fix for every `IllegalAccessException`: this is not a normal `Field.set` or `Method.invoke` operation. First determine whether the error is **lookup**, **proxy eligibility**, **access**, or **target exception**.
- When upgrading a library, adding a default override to a subinterface can make the old `Method` from the parent no longer a valid target to invoke. This is especially dangerous if a handler caches metadata by name/signature without re-checking the interface graph.

Projects that need compatibility across multiple interface versions should have **integration tests** for inherited default, override, duplicate signature, and newly added default methods. If an API is built to choose a specific implementation, record the interface selection policy explicitly instead of inferring it from `method.getDeclaringClass()` of the proxy-dispatched invocation.

## 10. Structuring a Real-World Handler

A production handler should separate its branches:

1. Handle `Object.equals`, `hashCode`, and `toString` with the desired semantics. They are dispatched into the handler with `Method` declared on `Object`; they are not default methods. If handler code calls `proxy.toString()` inside the `toString` branch for logging, it can accidentally recurse.
2. Handle methods with custom behavior/service delegation per contract and check return types.
3. For valid default methods, call `InvocationHandler.invokeDefault(proxy, method, args)`.
4. For unhandled abstract methods, throw a clear error such as `UnsupportedOperationException` instead of returning `null`; especially avoid `null` for primitive return types.
5. Preserve exceptions matching the interface and clarify the policy when multiple interfaces have methods with the same signature.

Handler skeleton (illustrative; not a standalone program):

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getDeclaringClass() == Object.class) {
        // Handle equals/hashCode/toString intentionally.
        return handleObjectMethod(proxy, method, args);
    }
    if (isCustomMethod(method)) {
        return invokeCustomBehavior(method, args);
    }
    if (method.isDefault()) {
        return InvocationHandler.invokeDefault(proxy, method, args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

The functions `handleObjectMethod`, `isCustomMethod`, and `invokeCustomBehavior` are only **illustrative extension points**; real implementations must be written. Do not drop this skeleton directly into a project without defining those functions. The program in section 7 is complete, runnable code.

**On performance:** `invokeDefault` is useful because it avoids requiring callers to construct `MethodHandles.Lookup`/adapters themselves to invoke default bodies on a proxy. However, there is still runtime overhead from the proxy/handler and potential additional dispatches from the default body back to the handler. Prioritize correct design and measure performance in the real system before optimizing.

## 11. Common Reasoning Pitfalls

| Misconception | Reality | Fix |
| --- | --- | --- |
| “If a proxy implements an interface, the default body runs automatically” | Every call through the interface goes to the handler | Branch on `method.isDefault()` and call `invokeDefault` if default behavior is desired |
| “Just calling `method.invoke(proxy, args)` runs the default body” | It can go back to the handler/recurse | Use `InvocationHandler.invokeDefault` for the default body |
| “`method.isDefault()` means it can be used on any proxy” | The method must belong to a valid proxy interface/inherited target | Check proxy interfaces and the override chain |
| “If the caller uses `Right`, the handler is guaranteed to receive `Right.label`” | Duplicate-signature methods depend on proxy interface order | Select `Right.class.getMethod(...)` if that is the required policy |
| “A parent default can always be called even if a child overrides it” | An override can make the equivalent `Parent.super` call invalid | Use the method belonging to the current implementation |
| “`args == null` always means missing arguments” | The handler can receive `null` for 0-parameter methods | Allow `null` for arity 0, check arity for other methods |
| “An array means multiple parameters of the target method” | An array can be **one parameter**; helper varargs easily spreads the array | Use `(Object) array` when calling directly |
| “`invokeDefault` always wraps target errors in `InvocationTargetException`” | The API propagates the default body's `Throwable` directly | Catch the actual exception, distinguish from `Method.invoke` |
| “`toString` is an interface default” | Proxy handles `Object` methods via the handler | Separate the `Object.class` branch |
| “Seeing `IllegalArgumentException` means the default body threw it” | It can be invalid proxy/method/args before invocation | Read the stack trace and check the failure stage |

## 12. Self-Check Exercises

**A.** `interface A { default String id(){ return "A"; } }`. The handler returns `"custom"` for every method and does not call `invokeDefault`. What does `((A) proxy).id()` return? Why?

**B.** The handler receives `method` as `A.id` and calls `method.invoke(proxy)`, while the handler runs the same logic every time. What is the risk? Why does it fail to invoke the default body properly?

**C.** A proxy implements `Left` and `Right`, both having `default String label()`. The handler wants to always return the `Right.label` body. What should it do instead of trusting that the caller's static type indicates which interface?

**D.** A proxy implements only `Child extends Parent`, and `Child` inherits `Parent.default m()`. Can `InvocationHandler.invokeDefault(proxy, Parent.class.getMethod("m"))` be valid? If `Child` overrides `m` with a new default, what changes?

**E.** A `default int twice(int n)` is called with `InvocationHandler.invokeDefault(proxy, method, (Object) null)`. Can we expect `0`? Why?

**F.** `default void run() { throw new IllegalStateException("bad"); }`. The handler calls `invokeDefault`. Is the exception in the handler `IllegalStateException` directly or `InvocationTargetException` by default?

**G.** The handler receives `args == null` for `default String ping()` with no parameters. Does it need to create `new Object[]{null}` to invoke the default?

**Answers:**

- **A:** Returns `"custom"`. The proxy does not run the default body automatically; the result is decided by the handler.
- **B:** It can recurse through the handler and eventually throw `StackOverflowError`. `Method.invoke(proxy)` still dispatches the call on the proxy; use `invokeDefault` to run the selected default body.
- **C:** Look up `Right.class.getMethod("label")` and pass that `Method` to `invokeDefault`, provided the proxy actually implements `Right` and the method is a valid default target.
- **D:** It can be valid when `Child` only inherits `Parent.m`. If `Child` overrides it, `Parent.m` may no longer be a valid default target and `invokeDefault` throws `IllegalArgumentException`; use `Child.m`.
- **E:** No. `null` cannot be unboxed to `int`; with invalid args, `invokeDefault` throws `IllegalArgumentException`.
- **F:** The default body throws `IllegalStateException`, and `invokeDefault` propagates that error directly. `InvocationTargetException` is a wrapper commonly seen from `Method.invoke`, not the default here.
- **G:** No. `null` as the argument list is accepted by the API when arity is 0. `new Object[]{null}` would become **one** argument, which is the wrong arity.

## 13. Official Java 17 Sources

- [Oracle Javadoc: `InvocationHandler.invokeDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html#invokeDefault(java.lang.Object,java.lang.reflect.Method,java.lang.Object...)): signature, `invokespecial`, inherited/default override, `args` rules, and exceptions.
- [Oracle Javadoc: `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dispatch to handler, duplicate-signature methods, `Object` methods, and module rules.
- [Oracle Javadoc: `Method.isDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isDefault()): identifying interface default methods.
- [Java SE 17 JLS `9.4.3 — Interface Method Body`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.3): rules for default methods in interfaces.

**Key takeaway:** Dynamic proxy **does not automatically run default bodies**; `InvocationHandler.invokeDefault(proxy, method, args)` executes a **valid default method** on the proxy itself via a special invocation. Select the `Method` of the right interface, pay attention to inherited/override/duplicate methods, pass the right count and types of args, and distinguish call preparation errors from exceptions thrown inside the default body.
