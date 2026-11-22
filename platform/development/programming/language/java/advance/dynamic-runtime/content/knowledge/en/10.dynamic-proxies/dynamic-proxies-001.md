# 10.1 Interface, proxy instance, `InvocationHandler`, and delegate model

**Context:** Java Advance → dynamic-runtime → 10. Dynamic proxies.

Java Dynamic Proxy (`java.lang.reflect.Proxy`) allows creating **an object at runtime that implements one or more interfaces**, then routing method calls on that object to an `InvocationHandler`. The handler decides how to process the call: it can return a synthetic result, log, enforce permissions, measure execution time, or **delegate** to a real object (delegate/target).

The most important point is to distinguish the four roles: **the interface defines the contract**, **the proxy instance is the object the caller holds**, **the InvocationHandler is the call dispatcher**, and **the delegate is the object executing business logic if the design uses delegation**. They have different responsibilities and should not be referred to interchangeably by the same name "proxy".

## 1. Four roles in the architecture

| Component | Nature | Responsibility | What not to misunderstand |
| --- | --- | --- | --- |
| **Interface** | A Java type contract, e.g. `Store` | Declares the methods the caller is allowed to invoke; specifies parameter, return, and checked exception types | An interface does not store a delegate or log on its own |
| **Proxy instance** | An object created by `Proxy.newProxyInstance(...)`; class generated at runtime | Implements the registered interfaces; receives calls matching interface signatures and routes them to the handler | The proxy is **not** the delegate object; it does not automatically extend the business class |
| **`InvocationHandler`** | An object implementing `InvocationHandler.invoke(proxy, method, args)` | Contains interception policy, routing, pre/post-processing, and exception handling | A handler is not required to use a delegate |
| **Delegate / target** | The real object, usually implementing the same interface | Executes business logic when the handler decides to delegate | Not every call on the delegate goes through the proxy; direct calls can bypass the handler |

Typical delegation call diagram:

```text
                       Store contract (interface)
                          ^               ^
                          | implements    | implements
                          |               |
Caller -------> proxy: Store                target: StoreImpl
   |                  |
   | proxy.find("A")  | dynamic dispatch to generated proxy method
   |                  v
   |          InvocationHandler.invoke(
   |              proxy, Method find, Object[]{"A"})
   |                  |
   |                  | validate / log / auth / metrics
   |                  v
   |              method.invoke(target, args)
   |                  |
   |                  v
   |           StoreImpl.find("A")
   |                  |
   |             result / exception
   |                  |
   +<---- handler returns / throws <----+
```

In this example, the caller **only knows `Store`**. It does not need to know the name of the generated proxy class or which delegate the handler uses. The handler is an **extension point** for cross-cutting concerns (logging, transaction, authorization, caching...) while preserving the statically typed API contract.

### Boundary choice: a proxy does not necessarily have a delegate

Java only requires `InvocationHandler` to handle the method and return an appropriate value or throw an appropriate exception. A handler can replace the entire call with a synthetic response, call a remote service, query a cache, or deny access. Therefore, it is necessary to distinguish:

- **Proxy with a delegate:** the handler invokes the real logic, adding behavior before/after.
- **Proxy without a delegate:** the handler provides the behavior itself, e.g. test/mock stubs, RPC clients, lazy endpoints.
- **Proxy with multiple delegates:** the handler selects a target based on the method, tenant, circuit breaker state, or routing strategy; this is still a single handler of the proxy.

In this lesson, we use the most common case: the handler **holds a reference to the delegate `StoreImpl`** and forwards business calls to it, while also showing a branch where the handler does not delegate.

## 2. Lifecycle of a dynamic proxy

A useful perspective is to distinguish **creation time** and **invocation time**.

**Step 1 — Define the contract:** Write an interface with the methods the caller needs to use.

```java
public interface Store {
    String find(String sku);
    int stock(String sku);
}
```

This is an **illustrative snippet**, not a standalone Java program following the structure shown. An interface can be shared by multiple implementations.

**Step 2 — Have a delegate:** A class such as `StoreImpl implements Store` is instantiated and ready to execute business logic.

**Step 3 — Have a handler:** Create an `InvocationHandler`. The handler can hold a reference to `StoreImpl`, as well as configuration information, permission checkers, loggers, metric registries, etc.

**Step 4 — Create the proxy instance:** Call:

```java
Store proxy = (Store) Proxy.newProxyInstance(
        Store.class.getClassLoader(),
        new Class<?>[]{Store.class},
        handler);
```

`Proxy.newProxyInstance` uses the class loader and the list of interfaces to provide an object implementing those interfaces, and attaches `handler` to the object. Calling `newProxyInstance` **does not mean invoking a business method**. The target is usually created separately beforehand; the proxy class and the delegate class are not the same type.

**Step 5 — Caller invokes through the interface:** For example `proxy.find("A")`. The proxy's method forwards the call to `handler.invoke(proxy, method, args)`.

**Step 6 — Handler decides:** If there is a delegate, the handler typically calls `method.invoke(delegate, args)` (or uses another dispatcher) and returns the result. It can validate input, enforce permissions, log, translate exceptions, or replace the result.

**Step 7 — Caller receives the result through the interface:** The caller still sees the `String` return type of `Store.find`, even though `InvocationHandler.invoke` returns `Object` internally.

Calling `delegate.find("A")` **directly** completely bypasses the handler. Therefore, you must pass **the reference to the proxy** to consumers that should be intercepted; if a consumer holds the original delegate and calls it, the interceptor has no opportunity to participate.

## 3. Understanding the three parameters of `InvocationHandler.invoke`

Standard signature:

```java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
```

| Parameter | Actual value | Proper usage |
| --- | --- | --- |
| `proxy` | The **proxy instance** that the caller just invoked, not the delegate | Identifying the proxy, handling `equals` by identity, invoking interface default methods via `InvocationHandler.invokeDefault` |
| `method` | `java.lang.reflect.Method` representing the invoked interface method; may represent `equals`/`hashCode`/`toString` of `Object` | Getting `getName()`, `getDeclaringClass()`, `getParameterTypes()`, `isDefault()`, or invoking on the delegate |
| `args` | `Object[]` containing the method arguments; **`null` if the method takes no parameters** | Handling `null` before iterating/logging, preserving order and value types |

For the call `proxy.find("A")`, the handler typically receives `method.getName().equals("find")` and `args[0].equals("A")`. For `proxy.refresh()` with no parameters, `args` can be **`null`**, not a zero-length array. When safe logging is needed:

```java
Object[] safeArgs = args == null ? new Object[0] : args;
System.out.println(java.util.Arrays.toString(safeArgs));
```

This is a **snippet** inside `invoke`, not a standalone runnable program.

### Primitive types, return types, and `void`

Because `invoke` returns `Object`, the Java proxy must map it back to the interface signature:

- If the interface takes a primitive (e.g. `int`), the value passed in `args` is boxed into its wrapper (`Integer`).
- If the interface returns `int`, the handler must return the **corresponding `Integer`** (or a valid object of the appropriate wrapper type); the generated proxy will unbox it to `int`.
- A handler returning `null` for a method with a primitive return type will cause the call on the proxy to throw `NullPointerException`.
- A handler returning an object that cannot be cast to the corresponding return type can cause `ClassCastException`.
- A `void` method does not require a meaningful return value; the handler should return `null` for clarity. `method.invoke(delegate,args)` naturally returns `null` for `void` methods.
- If a method returns a reference type, the handler can return `null` when the business contract allows it.

Do not assume that a dynamic proxy will automatically parse `"7"` into `int`, automatically handle nullable parameters, or perform conversions outside the interface contract. The handler is responsible for any additional steps.

### `Method` in the callback is not the "delegate's method"

Typically `method.getDeclaringClass()` is the interface declaring the method. The same interface method can be invoked on **any compatible delegate object**:

```java
Object result = method.invoke(delegate, args);
```

Condition: `delegate` must be an instance of the appropriate declaring interface/class; access rights and reflection rules still apply. If the handler chooses a delegate that does not implement the appropriate interface, `Method.invoke` can throw `IllegalArgumentException`. Do not use `method.invoke(proxy, args)` to "forward", because doing so usually **calls back into the proxy itself**, re-entering the handler and creating an infinite loop.

## 4. Complete Java 17 program: interface, proxy, handler, delegate

The standalone example below thoroughly verifies the roles of the four components, direct calls versus calls through the proxy, primitive/void return values, `Object` methods, default methods, and two exception policies.

Create the file **`DynamicProxyDemo.java`**. All types are placed in a single file so it can be copied, compiled, and run with Java 17 without libraries outside the JDK.

```java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Arrays;

public class DynamicProxyDemo {
    public interface Store {
        String find(String sku);
        int stock(String sku);
        void refresh();
        default String category() { return "general"; }
        String load(String sku) throws IOException;
    }

    static final class StoreImpl implements Store {
        @Override public String find(String sku) { return "item:" + sku; }
        @Override public int stock(String sku) { return 7; }
        @Override public void refresh() { System.out.println("delegate.refresh"); }
        @Override public String category() { return "special"; }
        @Override public String load(String sku) throws IOException {
            if ("missing".equals(sku)) throw new IOException("not found");
            return "loaded:" + sku;
        }
    }

    static final class LoggingHandler implements InvocationHandler {
        private final Store delegate;

        LoggingHandler(Store delegate) {
            this.delegate = delegate;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "StoreProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new AssertionError(method);
                };
            }
            Object[] safe = args == null ? new Object[0] : args;
            System.out.println("handler.before:" + method.getName() + ":" + Arrays.toString(safe));
            if ("find".equals(method.getName()) && "unhandled".equals(args[0])) {
                System.out.println("handler.throw:IOException");
                throw new IOException("synthetic");
            }
            try {
                Object result = method.isDefault()
                        ? InvocationHandler.invokeDefault(proxy, method, args)
                        : method.invoke(delegate, args);
                System.out.println("handler.after:" + method.getName() + ":" + result);
                return result;
            } catch (InvocationTargetException ex) {
                System.out.println("handler.cause:" + ex.getCause().getClass().getSimpleName());
                throw ex.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Store delegate = new StoreImpl();
        LoggingHandler handler = new LoggingHandler(delegate);
        Store proxy = (Store) Proxy.newProxyInstance(
                Store.class.getClassLoader(),
                new Class<?>[]{Store.class},
                handler);

        System.out.println("isProxy=" + Proxy.isProxyClass(proxy.getClass()));
        System.out.println("sameDelegate=" + (proxy == delegate));
        System.out.println("handlerMatches=" + (Proxy.getInvocationHandler(proxy) == handler));
        System.out.println("direct=" + delegate.find("A"));
        System.out.println("proxied=" + proxy.find("A"));
        System.out.println("stock=" + proxy.stock("A"));
        proxy.refresh();
        System.out.println("default=" + proxy.category());
        System.out.println("delegateDefaultOverride=" + delegate.category());
        System.out.println("toString=" + proxy);
        System.out.println("equalsSelf=" + proxy.equals(proxy));
        System.out.println("equalsDelegate=" + proxy.equals(delegate));
        System.out.println("hashCodeIdentity=" + (proxy.hashCode() == System.identityHashCode(proxy)));

        try {
            proxy.load("missing");
        } catch (IOException ex) {
            System.out.println("caller.declared=" + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }
        try {
            proxy.find("unhandled");
        } catch (UndeclaredThrowableException ex) {
            System.out.println("caller.undeclared=" + ex.getUndeclaredThrowable().getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 DynamicProxyDemo.java
java DynamicProxyDemo
```

**Exact stdout:**

```text
isProxy=true
sameDelegate=false
handlerMatches=true
direct=item:A
handler.before:find:[A]
handler.after:find:item:A
proxied=item:A
handler.before:stock:[A]
handler.after:stock:7
stock=7
handler.before:refresh:[]
delegate.refresh
handler.after:refresh:null
handler.before:category:[]
handler.after:category:general
default=general
delegateDefaultOverride=special
toString=StoreProxy
equalsSelf=true
equalsDelegate=false
hashCodeIdentity=true
handler.before:load:[missing]
handler.cause:IOException
caller.declared=IOException:not found
handler.before:find:[unhandled]
handler.throw:IOException
caller.undeclared=IOException
```

### Explanation of each output section

1. `isProxy=true`: the runtime class of `proxy` is a class generated by the `java.lang.reflect.Proxy` mechanism. **Do not** infer from class names like `$Proxy0`, because the name is an unstable implementation detail.
2. `sameDelegate=false`: `proxy` and `delegate` are two different objects. Both implement `Store`, but their reference identities do not match.
3. `handlerMatches=true`: `Proxy.getInvocationHandler(proxy)` returns the exact handler object used when creating the proxy.
4. `direct=item:A` has no `handler.before` line: calling via the `delegate` reference **bypasses the proxy**.
5. `proxied=item:A` has `handler.before:find:[A]` and `handler.after:find:item:A` logs: the call via `proxy` goes through the handler before/after the delegate runs.
6. `stock=7` demonstrates an interface method returning primitive `int`, while `Method.invoke` and `InvocationHandler.invoke` communicate via `Object` (appropriate boxing/unboxing).
7. `refresh()` has no parameters so `args` is `null`; the handler uses `safe` to log `[]`. The method returns `void` so `method.invoke` gives a `null` result, shown in `handler.after:refresh:null`.
8. `category()` is a **default method** on the interface. The handler calls `InvocationHandler.invokeDefault`, so the result is `general`, **not** calling the override `StoreImpl.category()` (which returns `special`). Therefore the two lines `default=general` and `delegateDefaultOverride=special` differ intentionally.
9. `toString`, `equals`, `hashCode` are answered specifically by the handler. This sample chooses identity equality, so `equalsSelf=true`, `equalsDelegate=false`, `hashCodeIdentity=true`; the results are deterministic.
10. `StoreImpl.load("missing")` throws `IOException("not found")`. `Method.invoke` wraps it in `InvocationTargetException`, the handler retrieves `getCause()` and rethrows `IOException`. Because `Store.load` **declares `throws IOException`**, the caller catches `IOException` directly.
11. The handler intentionally throws `IOException("synthetic")` for `Store.find("unhandled")`, while `Store.find` **does not declare** this checked exception. The proxy runtime wraps the error in `UndeclaredThrowableException`. This is an example explaining the `throws` contract, **not** business behavior to use in applications.

## 5. `Proxy.newProxyInstance`: what do the three arguments mean?

Signature:

```java
public static Object newProxyInstance(
        ClassLoader loader,
        Class<?>[] interfaces,
        InvocationHandler h);
```

### `loader`: proxy class loading context

`loader` is the class loader used to define the proxy class; it must be able to **resolve the exact `Class<?>` object of each interface** by name (tied to class loader identity). In typical applications, `MyApi.class.getClassLoader()` is the natural choice if the proxy implements `MyApi`. In plugin systems, a different loader may need to be designed appropriately so that both the caller and the proxy see the same shared interface.

Do not automatically take the delegate's loader if it does not see the interface with the same runtime type identity. Two classes with the same fully-qualified name defined by different loaders can be two different runtime types. The proxy might fail to be created or fail to be cast to the interface the caller expects.

### `interfaces`: list of public contracts the proxy exposes

For example, `new Class<?>[]{Store.class}` requests the proxy to implement `Store`. Multiple interfaces can be registered in one proxy if the constraints on method compatibility, class loader, and package/module are satisfied.

Basic rules:

- Each element must be an **interface**, not a concrete class like `StoreImpl.class`.
- The list must not contain duplicate interfaces.
- Non-public interfaces included in a proxy are subject to stricter package/module constraints; you cannot arbitrarily combine package-private interfaces from incompatible packages/modules.
- Overlapping signatures from multiple interfaces must have compatible return types according to Proxy API rules; otherwise, proxy creation may be rejected.
- **The order of interfaces in the array matters**, especially when multiple interfaces have methods with matching signatures: the `Method` received by the handler does not always reflect the exact static interface type that the caller used.

When an exercise requires multiple interfaces, write unit tests for overlapping signatures and check `method.getDeclaringClass()`, rather than dispatching solely by `getName()`.

### `h`: handler attached to each proxy instance

This is the object containing the interception mechanism. A handler can be shared across multiple proxy instances if logic and state allow. Even though a handler object is a normal Java instance, you should not share non-thread-safe mutable state if multiple threads can invoke the proxy.

Creating a proxy requires `h` to be non-`null`; passing invalid class loader/interface parameters or duplicates can cause `IllegalArgumentException` or module/visibility check errors. The standard workflow is to create a proxy from a defined list of interfaces and a non-null handler, then cast it to one of the declared interfaces.

### Proxy does not extend `StoreImpl`

A JDK dynamic proxy is a subclass of `java.lang.reflect.Proxy` and implements the specified interfaces. It **does not extend `StoreImpl`**, does not copy fields from the delegate, and cannot be cast to `StoreImpl`. For example:

```java
Store proxiedStore = (Store) Proxy.newProxyInstance(
        Store.class.getClassLoader(),
        new Class<?>[]{Store.class},
        handler);

// Valid: caller holds the Store interface type.
// Invalid: (StoreImpl) proxiedStore
```

The snippet above assumes the types `Store`, `StoreImpl`, and the variable `handler` already exist from the application; it is **not** a standalone program. When you need to create a proxy for a class without an interface, JDK `Proxy` is not the appropriate tool; you need to change the API to an interface or consider separate subclass/bytecode generation mechanisms and their limitations.

## 6. `InvocationHandler` does not require delegation: typical handler structure

A minimal handler can be written as:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("find")) {
        return "fixture-value";
    }
    throw new UnsupportedOperationException(method.getName());
};
```

This is an **illustrative snippet** of a mock handler, not a standalone application. If attached to the `Store` interface, the handler returns a string directly for `find` without calling `StoreImpl`. Every other method will fail if the caller invokes it; therefore, production code must clearly define the handling policy for all supported interface methods (including `Object` methods).

A delegating handler typically has the following logical steps:

```text
invoke(proxy, method, args)
   |
   +-- Object.equals / hashCode / toString?
   |      +-- identity or semantic equality policy
   |
   +-- Authorization check / validate / pre-log
   |
   +-- Default method?
   |      +-- invoke the interface's default method, if intended
   |
   +-- Delegate branch
   |      +-- method.invoke(delegate, args)
   |      +-- unwrap InvocationTargetException
   |
   +-- Record result / metrics
   |
   +-- Return an object compatible with the interface's return type
```

Depending on the application, you can omit the default branch, switch delegates, attach a cache, return a synthetic response, or call a remote client. What matters is that the **method contract** must still be preserved: return type, checked exceptions, thread-safety, and identity semantics.

## 7. Three groups of calls to handle carefully

### 7.1 Business methods declared in the interface

Methods such as `find`, `stock`, and `load` appear in `Store`. In the handler, `method` corresponds to the interface method. If the delegate implements the same interface, `method.invoke(delegate,args)` is a straightforward way to delegate, though `InvocationTargetException` must be handled.

For overloaded methods, **do not dispatch by name alone**. For example, two methods `find(String)` and `find(long)` have the same name; distinguish them by `method.getParameterTypes()`, `method.getReturnType()`, or by comparing against previously looked-up `Method` objects. Dispatching based on `getName()` is sufficient for small examples, but error-prone as the API grows.

### 7.2 `Object` methods: `equals`, `hashCode`, and `toString`

Calls to these three methods on the proxy are also sent to the handler; the corresponding `Method` has `getDeclaringClass() == Object.class`. This holds true even if the interface declares a method with the same public signature.

In the program above, the handler chooses:

```java
case "toString" -> "StoreProxy";
case "hashCode" -> System.identityHashCode(proxy);
case "equals" -> proxy == args[0];
```

This snippet is part of the `switch` in `InvocationHandler.invoke`. It provides a consistent **identity equality** policy: the proxy is only equal to itself and `hashCode` follows identity. For a proxy acting as a value object, an application can choose semantic equality, but must ensure `equals` is symmetric, transitive, consistent, and compatible with `hashCode`.

**Common mistake:** Inside the handler, logging like `System.out.println(proxy)` calls `proxy.toString()`, which routes back into the handler itself. If the `toString` branch also logs `proxy`, it can lead to infinite recursion. Use a safe identifier or call `System.identityHashCode(proxy)` instead of printing `proxy` directly inside the handler. Also do not call `method.invoke(proxy,args)` to delegate, as that will route back to the handler.

Other `Object` methods like `getClass()` are not proxy-overridden methods dispatched through the handler in the same way; `getClass()` is `final` and will reflect **the proxy's class**, not the delegate's.

### 7.3 Default methods on interfaces

Java interfaces can declare `default` methods, such as `Store.category()`. The proxy still routes default method calls to the handler; the handler must choose **how to execute them**.

There are two distinct options:

- **Delegate through the delegate:** `method.invoke(delegate,args)` dispatches according to the delegate's implementation, including the delegate's **override**. In the demo, `StoreImpl.category()` returns `"special"`.
- **Invoke the interface's default method via the proxy:** `InvocationHandler.invokeDefault(proxy, method, args)` invokes the exact default implementation permitted on the proxy; in the demo it returns `"general"`.

`InvocationHandler.invokeDefault` has been available since Java 16, so it works well on Java 17. The method passed in must be a valid default method declared or inherited by a proxy interface; the API has specific constraints with multi-level method overrides. Do not use `method.invoke(proxy,args)` to "call default" because that dispatches back to the handler.

Do not assume a dynamic proxy "automatically runs the default method when there is no override". The handler still controls the call; if the handler does not actively invoke the default method or delegate, the default body may never execute.

## 8. Exceptions when the delegate or handler fails

There are **two layers of communication** to distinguish:

1. **Handler → delegate via Reflection:** `method.invoke(delegate,args)`.
2. **Proxy → caller:** the handler returns an object or throws a `Throwable` out of `InvocationHandler.invoke`.

If the delegate's body throws an exception, `Method.invoke` typically wraps the actual error in `InvocationTargetException`. The handler should retrieve `getCause()` and handle/rethrow **the business cause**, rather than letting the Reflection wrapper leak out in a way that violates the `throws` contract:

```java
try {
    return method.invoke(delegate, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

This snippet belongs inside `InvocationHandler.invoke` with `throws Throwable`, not a standalone program.

### Checked exceptions rules

| Exception thrown by handler | Interface method declares | What does the caller see? |
| --- | --- | --- |
| `RuntimeException` or `Error` | No declaration needed | Unchecked error propagates directly |
| `IOException` | Has `throws IOException` | `IOException` reaches the caller |
| `IOException` | Does not have `throws IOException` (or a compatible supertype) | Proxy wraps it in `UndeclaredThrowableException` |
| Unwrapped `InvocationTargetException` | Method only declares `IOException` | The wrapper is another checked exception; may be wrapped by proxy in `UndeclaredThrowableException` |
| `IllegalArgumentException` from handler | No declaration needed | Propagates as an unchecked exception |
| `NullPointerException` due to handler dereferencing null | No declaration needed | Propagates as an unchecked exception |

The main pattern is **not to expose `InvocationTargetException` outside the handler if it is only the wrapper created by `Method.invoke`**. However, if target code intentionally throws an `InvocationTargetException` as a business exception (rare), it should be classified according to the actual design.

In the program:

- `load("missing")`: the delegate throws `IOException`, the handler unwraps it, the interface declares the checked exception → the caller catches `IOException`.
- `find("unhandled")`: the handler intentionally throws `IOException` but `find` does not declare it → the caller sees `UndeclaredThrowableException`. Use `getUndeclaredThrowable()` to inspect the original exception.

If a proxy implements **multiple interfaces that have methods with the same signature** but declare different checked exceptions, the set of checked exceptions the handler is allowed to throw may be more restricted than for a single interface. Consult the `Proxy` Javadoc and write tests before combining complex interfaces.

### Return type and argument errors

Both `InvocationHandler.invoke` and `Method.invoke` use an object-level API, yet the interface's method contract remains strict:

- For `Store.stock(String)` returning `int`, the handler needs to return `Integer`. Returning `"7"` does not automatically parse into `int`.
- If the handler returns `null` for `int`, the caller receives `NullPointerException` when the proxy unboxes it.
- If the handler returns an object incompatible with `String`, the caller receives `ClassCastException`.
- `args` being `null` for a zero-parameter method does not mean the caller passed a `null` argument.
- If the delegate does not implement the declaring interface of `method`, `method.invoke(delegate,args)` cannot form a valid call and may throw `IllegalArgumentException`.

You should separate proxy binding/compatibility errors, Reflection errors in the handler, and business errors thrown by the delegate.

## 9. API visibility, class loader, and module rules

Dynamic proxy is a runtime tool, but **it does not bypass Java access controls on its own**. When designing contracts in a plugin system, microservice client, or framework:

1. **The interface must share the exact same runtime type identity:** the caller, handler, and proxy must agree on the same `Class<?>` for the interface. With plugin loaders, do not compare names by string alone.
2. **The class loader creating the proxy must be able to see the required interfaces.** If the loader resolves the same name to a different class, proxy creation or casting may fail.
3. **Non-public interfaces have package/module constraints.** You cannot assume an arbitrary loader can implement any set of private interfaces.
4. **JPMS has its own `exports`/`opens`:** Public APIs in named modules must be accessed according to module rules. If a handler needs reflection into private members of the delegate, `setAccessible`/`privateLookupIn` is subject to the corresponding module/open-package conditions.
5. **Do not equate the visibility of the interface with the visibility of the implementation.** The caller works through the interface; the handler can keep the implementation package-private/private internally when permissions and delegation mechanisms allow.
6. **Do not cast the proxy to the implementation class.** Even when the target and proxy implement the same interface, their class identities are different.

**Package design example:** Put `api.Store` as the shared contract (and export it if it is a named module); put `impl.StoreImpl` on the implementation side; provide a factory that returns a `Store` proxy to the caller. Consumers do not need to know `StoreImpl` or the specific handler class. This is how cross-cutting concerns are separated from business code.

## 10. Important limitations of JDK Dynamic Proxy

### Only proxies interfaces, does not automatically proxy concrete classes

`java.lang.reflect.Proxy` creates instances that implement interfaces. It does not create subclasses of a `final class` or intercept methods not in the contract interface when callers access the object via a concrete class type. If you need to intercept methods of an implementation class that are not in an interface, JDK Dynamic Proxy cannot do that just by creating a proxy.

Some frameworks use subclass proxies or separate bytecode generation to support other scenarios. That is a **different mechanism**, with its own constraints regarding `final`, constructors, modules, and identity; it should not be confused with core JDK interface proxies.

### Internal calls and self-invocation

Suppose `StoreImpl.find` calls `this.stock(...)` on the same implementation object. If the handler only forwards `find` via `method.invoke(delegate,args)`, the `this.stock` call inside the delegate **does not go through the proxy**; it is an internal call on the delegate. This is a common pitfall when applying logging, authorization, or transactions at the proxy layer: only **calls that actually go through the proxy reference** are intercepted.

If internal calls also need to go through the interceptor, you must redesign the call site, use a controlled proxy reference, or move the critical behavior into a separate domain/service class. Do not try to "fix" it by having the handler call back into the proxy itself without a loop-termination strategy.

### Proxies do not make code thread-safe

Proxies and handlers can be used from multiple threads. If a handler stores a mutable cache, sequence number, or non-thread-safe delegate, dynamic proxy **does not** synchronize them automatically. For logging and metrics, prefer thread-safe counters/registries; for the delegate, apply the concurrency rules of that service.

### Performance depends on workload

Going through a proxy introduces at least one dispatch layer to the handler and may add Reflection invocation, logging, or validation. The JIT can optimize some stable call paths, but you cannot generalize that all proxies are "faster" or "too slow to use". Measure in a production-like environment and avoid recreating proxies on every call if the proxy and its configuration are long-lived.

### Lifecycle and class loader management

The JDK has a mechanism for managing proxy classes per loader/interface combination; you should not indefinitely hold strong reference caches to class loaders, proxy instances, `Method` objects, or handlers of unloaded plugins. In hot-reload systems, ensure the lifecycle of the proxy/handler/delegate aligns with the class loader lifecycle to avoid retaining old plugin versions in memory.

## 11. Anti-patterns and fixes

| Anti-pattern | Why it is wrong | How to fix |
| --- | --- | --- |
| Handler calls `method.invoke(proxy,args)` to delegate | Dispatches back to proxy → handler recursion | Invoke on `delegate` or execute another explicit branch |
| Handler assumes `args.length` is always valid | Zero-parameter methods have `args == null` | Normalize null to an empty array when needed |
| Logging `proxy.toString()` inside `toString` handling | Can recurse through the handler itself | Separate the `Object` branch, use safe identity metadata |
| Returning `null` for a method returning `int` | Proxy needs to unbox wrapper → NPE | Return an `Integer` with an appropriate value |
| Returning `String` for a method returning `long` | Incompatible return type → ClassCastException | Normalize the type in the handler to match the interface |
| Throwing raw `InvocationTargetException` from delegate | Hides the business exception and may be wrapped by proxy | Unwrap `getCause()` when forwarding |
| Handler throws a checked exception not declared by the method | Proxy will wrap it in `UndeclaredThrowableException` | Preserve the `throws` contract, use unchecked domain exceptions if appropriate |
| Casting proxy to `StoreImpl` | Proxy only implements interfaces, does not extend implementation | Caller keeps the `Store` type |
| Calling `delegate` directly while expecting proxy logs | Bypasses interception | Pass the proxy where consumers invoke it |
| Dispatching solely by `method.getName()` | Overloads/duplicate signatures may be mishandled | Inspect full signature and interface context |
| Believing default methods run automatically | Default calls are sent to the handler | Choose `invokeDefault` or delegate intentionally |
| Using an arbitrary class loader | Does not see the same interface runtime type | Use a loader compatible with the API contract |
| Holding mutable state in an unsynchronized singleton handler | Race condition | Design thread-safely or scope the handler |
| Treating dynamic proxy as a hard security boundary | Callers might hold the original delegate and bypass the proxy | Enforce protection at the service/data layer and do not leak bypass references |

## 12. Debugging a call that does not go through the handler

Investigate in order:

1. **Is the object the caller holds a proxy or a delegate?** Use `Proxy.isProxyClass(obj.getClass())` when `obj` is valid. If `false`, the caller may be using the implementation object directly.
2. **Which interfaces was the proxy created for?** Check the interface list in the factory and the reference type the consumer receives.
3. **Is the handler attached to the right instance?** For an object verified to be a proxy, `Proxy.getInvocationHandler(proxy)` can help cross-check.
4. **Is the call an interface method?** Final methods of `Object` such as `getClass()` are not dispatched through the handler like interface methods.
5. **Are there internal calls inside the delegate?** Calls on `this` can bypass the proxy.
6. **Does the handler have an early-return branch or cache hit?** Not seeing delegate logs does not necessarily mean the handler did not run.
7. **Is the handler creating a loop?** Check `method.invoke(proxy,args)` and how `toString`/`equals` are handled.
8. **Are there overloaded methods or duplicate signatures?** Log `method.toGenericString()`, `method.getDeclaringClass()`, and the `getParameterTypes()` list.
9. **Which layer is the exception at?** `InvocationTargetException` in Reflection delegation, `UndeclaredThrowableException` at the proxy boundary, or return type errors when the generated proxy converts from `Object` to the contract type.
10. **If the error is specific to plugins/modules, verify the class loader, module exports/opens, and runtime class identity.**

The following debug snippet is a **snippet** inside a handler that already has `method` and `args`, not a standalone application:

```java
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("signature=" + method.toGenericString());
System.out.println("default=" + method.isDefault());
System.out.println("argCount=" + (args == null ? 0 : args.length));
```

Avoid printing the entire `args` in production if arguments contain passwords, tokens, PII, or objects with expensive/side-effecting `toString`. Log the method name, argument count, duration, or permitted metadata instead of leaking data.

## 13. Knowledge check exercises

**Question 1.** Interface `Service` has method `run()`. A consumer holds the reference `Service proxy`. Which objects will a call to `proxy.run()` pass through in a model with a delegate?

**Answer:** Caller → proxy instance → `InvocationHandler.invoke` → delegate (if the handler chooses to delegate) → handler → proxy/caller. The interface is a type contract, not a separate runtime execution object.

**Question 2.** Is a handler required to hold a delegate?

**Answer:** No. A handler can return a synthetic response, call a remote service, mock behavior, or deny access. A delegate is just one design choice.

**Question 3.** In `InvocationHandler.invoke`, is the `proxy` parameter the target implementation?

**Answer:** No. `proxy` is the runtime proxy object that the caller just invoked. The delegate is a separate reference held or selected by the handler.

**Question 4.** An interface has `void refresh()`. What is the value of `args` in the handler and what should the handler return?

**Answer:** For a zero-parameter method, `args` is `null`. The handler should return `null` for `void`, and can normalize it to an empty array when iterating/logging is needed.

**Question 5.** An interface has `int stock()`. What happens if the handler returns `null`?

**Answer:** When the proxy converts the `Object` value to primitive `int`, `null` cannot be unboxed → `NullPointerException`.

**Question 6.** Can an instance created by `Proxy.newProxyInstance` be cast to `StoreImpl`?

**Answer:** No, except for special type relationships that do not apply in the standard JDK proxy model: the proxy implements `Store`, it does not extend `StoreImpl`. Work through the interface.

**Question 7.** Why does `method.invoke(proxy, args)` inside a handler risk a `StackOverflowError`?

**Answer:** It invokes the method on the proxy itself, the proxy calls the handler again, the handler invokes the proxy again... Execution never reaches the delegate without a proper terminating branch.

**Question 8.** Default method `Store.category()` returns `"general"`, while `StoreImpl` overrides it to return `"special"`. What should you do in Java 17 to invoke the interface's default method directly on the proxy?

**Answer:** Inside the handler, use `InvocationHandler.invokeDefault(proxy, method, args)` with a valid default `method`. Calling `method.invoke(delegate,args)` dispatches to the delegate's implementation and can return `"special"`.

**Question 9.** The delegate throws `IOException` and the interface method has `throws IOException`. The handler used `method.invoke(delegate,args)`. What must be done so the caller receives the `IOException` properly?

**Answer:** Catch `InvocationTargetException` and rethrow `ex.getCause()`. Because the interface declares that checked exception, the proxy passes it to the caller per the contract.

**Question 10.** A handler throws a checked `IOException` for an interface method that declares no checked exceptions. What does the caller see?

**Answer:** `UndeclaredThrowableException`, with `getUndeclaredThrowable()` containing the original `IOException`.

**Question 11.** Are all internal `this.method()` calls inside a delegate intercepted just because the delegate was called through a proxy?

**Answer:** No. Only calls through the proxy reference go to the handler. Internal calls on the delegate can execute directly without going through the proxy.

**Question 12.** Does a proxy class have the same class name across runs? Should you rely on the name `$Proxy0`?

**Answer:** You should not. The runtime-generated name/class is an implementation detail; use `Proxy.isProxyClass`, the interfaces, and `Proxy.getInvocationHandler` to verify instead of parsing the generated class name.

**Question 13.** An interface `Repository` and a class `RepositoryImpl` are loaded across multiple class loaders. Why does calling `Proxy.newProxyInstance` sometimes fail even though the interface name is the same?

**Answer:** Runtime type identity includes the defining class loader. The loader used to create the proxy must resolve **the exact `Class<?>` of the interface** agreed upon by the caller and handler; matching string names is not enough.

**Question 14.** Can you combine two interfaces into one proxy and distinguish methods solely by name?

**Answer:** You should not. There may be overloads and duplicate signatures; you need to inspect the full method signature, declaring interface, and compatibility rules. In some cases, the proxy runtime passes a `Method` representing the interface that appears earlier in the list.

**Question 15.** A handler uses `proxy.equals(delegate)` to check if the delegate is the same object. Why does it return `false` in the demo?

**Answer:** The demo chooses identity equality: the handler returns `proxy == args[0]`. The proxy and the delegate are two different instances. A model can certainly choose a different semantic equality, but it must preserve the `equals`/`hashCode` contract.

## 14. Key takeaways

- **Interface** is the contract; **proxy instance** is the object the caller uses; **InvocationHandler** receives and handles calls; **delegate** is the business object if the handler decides to delegate.
- `Proxy.newProxyInstance(loader, interfaces, handler)` creates a proxy implementing the specified interfaces; it **does not** turn the delegate into a proxy and **does not** create a subclass of the implementation class.
- `invoke(proxy, method, args)` receives the proxy instance, `Method`, and `Object[]`; for zero-parameter methods, `args` can be `null`.
- When delegating, use `method.invoke(delegate, args)`, **not** `method.invoke(proxy,args)`; if the delegate throws an error, consider unwrapping `InvocationTargetException`.
- The interface's return types and `throws` clauses are still enforced: primitives need wrappers, and undeclared checked exceptions are wrapped in `UndeclaredThrowableException`.
- `equals`, `hashCode`, and `toString` of the proxy go through the handler; there must be a safe identity/equality policy that avoids recursion.
- Default methods are still decided by the handler; Java 17 provides `InvocationHandler.invokeDefault` to invoke the interface's default implementation directly.
- **Direct calls, self-invocation, and implementation-only methods do not automatically go through the proxy.** Consumers need to hold the proxy reference for interception to work.
- Class loaders, interface visibility, and module boundaries are critical in applications with plugins/hot reload; proxies do not automatically bypass Java access controls.

### Official documentation (Java SE 17)

- [Oracle — `java.lang.reflect.Proxy`, dynamic proxy classes and `newProxyInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Oracle — `InvocationHandler.invoke` and `InvocationHandler.invokeDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Oracle — `Method.invoke` and `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Oracle — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)