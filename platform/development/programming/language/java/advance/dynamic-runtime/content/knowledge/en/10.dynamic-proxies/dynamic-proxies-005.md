# 10.5. Delegating Calls to the Right Object and Avoiding Infinite Recursion via Dynamic Proxy

In Java, a **dynamic proxy** from `java.lang.reflect.Proxy` creates an object implementing one or more interfaces. Whenever a client invokes a method through the proxy object, the JVM forwards the call to `InvocationHandler.invoke(proxy, method, args)`. The handler can log, measure time, check permissions, or forward the call to the **real implementation object (target/delegate)**.

The most common mistake is confusing the two objects:

- `proxy` in the `InvocationHandler.invoke` parameter is **the proxy object itself that received the call**, not the backend.
- `target` is **the real object** held separately by the application to perform the business logic.

When the handler uses `method.invoke(proxy, args)` instead of `method.invoke(target, args)`, the call goes back to **the same handler**, then the handler calls the proxy again and continues without stopping. The result can be infinite recursion, `StackOverflowError`, or complex exception layers due to Reflection wrapping errors.

The goal of this lesson is to understand the call path correctly, implement a safe delegating handler, distinguish **reentrancy due to misconfiguration** from **valid nested calls**, handle special cases (`equals`, `hashCode`, `toString`, default methods, exceptions), and know how to test using Java 17+.

## 1. What components does a dynamic proxy consist of?

Suppose the business interface is `Service`, and the real implementation is `RealService`.

```text
Client
  |
  | service.work("A")
  v
Service proxy (object created by Proxy.newProxyInstance)
  |
  | InvocationHandler.invoke(proxy, method, args)
  v
DelegatingHandler
  |
  | method.invoke(target, args)
  v
RealService target
  |
  | executes business logic
  v
Result / exception
  |
  +--------------------------> returned to client
```

`Proxy.newProxyInstance(ClassLoader, Class<?>[], InvocationHandler)` creates a proxy object for **interfaces**, not by automatically subclassing any arbitrary Java class. `Service` is implemented at runtime by a JDK-generated proxy class; the implementation object `RealService` does not become a proxy just because it is referenced by the handler.

`InvocationHandler` defines:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

Three parameters need to be understood separately:

| Parameter | What is it exactly? | Notes when delegating |
| --- | --- | --- |
| `proxy` | The proxy object that the client just called | **Do not use it as the receiver** for `Method.invoke` if intending to call the real target |
| `method` | `java.lang.reflect.Method` metadata representing the call via the interface or certain methods of `Object` | Use both name **and signature** to identify; do not check only the name when there are overloads |
| `args` | Array of arguments boxed as needed, or `null` if the method has no parameters | Pass the exact array to `Method.invoke`; do not wrap it in another array layer |

The object returned from the handler must be compatible with the return type of the method on the interface. For `void`, the handler can return `null`. For primitive returns, the proxy must have an appropriate wrapper value to unbox; returning `null` for a method returning `int`/`boolean` can lead to `NullPointerException`.

**A handler does not necessarily only do delegation**: it can handle some methods directly in the handler, call default interface methods, or reject operations. But if it chooses to forward to the backend, **the correct receiver is the backend**.

## 2. The loop-creating mistake: `Method.invoke(proxy, args)`

Typical error pattern:

```java
InvocationHandler bad = (proxy, method, args) ->
        method.invoke(proxy, args); // WRONG: calls the proxy itself again
```

This snippet is an **anti-example**, do not run it freely in a real program. Execution flow:

```text
client -> proxy.work()
            |
            v
          handler.invoke(proxy, work, args)
            |
            | method.invoke(proxy, args)
            v
          proxy.work()
            |
            v
          handler.invoke(proxy, work, args)
            |
            | method.invoke(proxy, args)
            v
          proxy.work()
            |
           ...
```

`Method.invoke` has no rule saying "if the receiver is a proxy, go straight to the implementation". It executes the call on **the provided receiver**. If the receiver is the proxy, the proxy still dispatches to the handler. Without a stopping condition, the loop will repeat until the stack or related resources are exhausted.

Changing the receiver to `target` solves the **direct loop**:

```java
InvocationHandler good = (proxy, method, args) ->
        method.invoke(target, args); // RIGHT RECEIVER if target is compatible
```

This is an **illustrative snippet** using an existing `target` variable. In production, you also need to handle `InvocationTargetException`, `Object` methods, default methods intentionally, and check the target type. The complete program in section 4 implements these parts.

Important note: `target != proxy` is a necessary condition to avoid a direct loop **in this delegation approach**, but **does not guarantee there is no indirect cycle**. For example, proxy A delegates to proxy B, and B's handler delegates back to A, still creating a cycle. You need to evaluate **the overall path** of delegation.

## 3. The right receiver and mistakes when choosing a target

With `method` representing an **instance method** of an interface, `method.invoke(receiver, args)` requires `receiver` to be an object on which that method can be invoked. If the backend `RealService implements Service` and the method is obtained from `Service`, the reflective call on the backend is appropriate.

Different receiver choices:

| Receiver | Typical result |
| --- | --- |
| Real `target`, implementing the corresponding interface | Runs the business method on the backend |
| Current `proxy` | Handler is called again, easily becoming an infinite recursion loop |
| `null` for an instance method | Not a valid receiver; can cause `NullPointerException` |
| Object incompatible with the class/interface declaring the method | `IllegalArgumentException` |
| Another proxy whose handler continues to a real backend | Can be a **valid proxy chain** if the graph does not form a cycle |
| Another proxy whose handler forwards back to the current proxy | **Indirect cycle**, still risks infinite recursion |

Do not "fix" a receiver type error by calling `method.invoke` on an arbitrary object that has a method **with the same name**. `Method` is bound to the declaring class/interface and signature. If the target does not implement the proxied interface, you must define a **valid adapter/mapping**, look up the `Method` on the right target class with the exact parameter list and check access; avoid calling the wrong overload. In this lesson, we intentionally choose a target implementing the same interface to keep delegation clear.

If the backend itself is another dynamic proxy, delegation can still be valid, but you need to determine whether that proxy terminates at a real implementation or continues looping. Do not use `Proxy.isProxyClass(...)` to conclude that "all proxy targets are wrong", because decorator/transaction chains can be designed properly.

## 4. Complete Java 17+ example: proper delegation, Object methods, default method, and safely detected loop

Create a file named exactly **`ProxyDelegationDemo.java`**. All interfaces, implementations, and both handlers reside together in one public class, so it can be compiled immediately with JDK 17+ on the classpath, without external libraries.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class ProxyDelegationDemo {
    public interface Service {
        String work(String value);
        String inner(String value);
        String outer(String value);
        void fail();

        default String decorated(String value) {
            return "<" + work(value) + ">";
        }
    }

    public static final class RealService implements Service {
        @Override
        public String work(String value) {
            return "work:" + value;
        }

        @Override
        public String inner(String value) {
            return "inner:" + value;
        }

        @Override
        public String outer(String value) {
            return "outer(" + inner(value) + ")";
        }

        @Override
        public void fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static final class DelegatingHandler implements InvocationHandler {
        private final Service target;

        public DelegatingHandler(Service target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            // Object methods are defined by the proxy's identity.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "ServiceProxy";
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            System.out.println("log:" + method.getName());

            // Intentionally run default method on the proxy (Java 16+).
            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, args);
            }

            // For business methods, the receiver MUST be the real target.
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            }
        }
    }

    public static final class LoopingHandler implements InvocationHandler {
        private int calls;

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            // For demo only: detect after three re-entries,
            // avoiding running into a real StackOverflowError.
            if (++calls > 3) {
                throw new IllegalStateException("proxy re-entered");
            }
            try {
                return method.invoke(proxy, args); // Intentionally wrong!
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Service real = new RealService();

        Service service = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                new DelegatingHandler(real));

        System.out.println("work=" + service.work("A"));
        System.out.println("outer=" + service.outer("B"));
        System.out.println("decorated=" + service.decorated("C"));

        try {
            service.fail();
        } catch (IllegalStateException exception) {
            System.out.println("caught=" + exception.getMessage());
        }

        System.out.println("toString=" + service.toString());
        System.out.println("equalsSelf=" + service.equals(service));
        System.out.println("equalsTarget=" + service.equals(real));
        System.out.println("hashIdentity=" +
                (service.hashCode() == System.identityHashCode(service)));
        System.out.println("sameObject=" + (service == real));

        // Create an intentionally broken proxy, but with a clear stopping point.
        Service broken = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                new LoopingHandler());
        try {
            broken.work("X");
        } catch (IllegalStateException exception) {
            System.out.println("recursionDetected=" + exception.getMessage());
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 ProxyDelegationDemo.java
java ProxyDelegationDemo
```

**Actual stdout**, verified:

```text
log:work
work=work:A
log:outer
outer=outer(inner:B)
log:decorated
log:work
decorated=<work:C>
log:fail
caught=boom
toString=ServiceProxy
equalsSelf=true
equalsTarget=false
hashIdentity=true
sameObject=false
recursionDetected=proxy re-entered
```

### 4.1. The `work` line proves basic delegation

The client calls `service.work("A")`; because `service` is a proxy, the handler receives `method=Service.work`, along with argument `"A"`. The handler logs `log:work`, then `method.invoke(target, args)` calls `RealService.work("A")`. Returns `work:A`.

The key point: the handler **does not call `service.work("A")` again**. If the handler used `method.invoke(proxy, args)`, the proxy itself would call the handler again.

### 4.2. `outer` calls `inner` without an extra `log:inner`: this is not a recursion loop

`RealService.outer` executes on **the real target**, and inside it writes `inner(value)` which is equivalent to a call on `this` (i.e., `RealService`). Internal calls **do not automatically go back through the proxy**. Therefore:

```text
log:outer
outer=outer(inner:B)
```

there is no `log:inner` line.

This is **self-invocation bypass**: proxy-based interceptors (logging, transactions, authorization, metrics) will not automatically apply to internal `this.inner(...)` calls on the target. This may be intentional or a design risk, but **it is not an infinite recursion bug**.

If every call to `inner` must go through the interceptor, the architecture must change: extract a proxy-wrapped collaborator, route the call through a controlled injected proxy, or apply a different interception mechanism. **Do not fix it by changing all `Method.invoke(target, args)` to `Method.invoke(proxy, args)`**, as that will create a loop at the very first entry point.

### 4.3. `decorated` has two logs because it intentionally invokes the default method on the proxy

The `Service` interface declares:

```java
default String decorated(String value) {
    return "<" + work(value) + ">";
}
```

This is a default method of the interface, not a separate override of `RealService`. The handler chooses:

```java
InvocationHandler.invokeDefault(proxy, method, args)
```

This API has existed since Java 16 and is supported on Java 17+. It **directly invokes the default implementation** of the interface like an `Interface.super.method(...)` call on **the proxy**, instead of replaying `method.invoke(proxy, args)` through the handler for the `decorated` method itself.

Because the default method body uses `work(value)` on `this`, which is the proxy, the `work` call continues into the handler. Hence the trace:

```text
log:decorated
log:work
decorated=<work:C>
```

This is **useful, terminating reentrancy**: `decorated` calls *another* method, and then `work` is forwarded by the handler to the backend. Do not use a guard that "blocks every nested handler call", because it will break valid cases like this.

If replaced with `method.invoke(target, args)` for the default method, the default method body is invoked on **the target**, so the `work` call inside will usually go straight to the target and **will not produce `log:work`**. The two strategies have different semantics; choose according to interceptor needs, do not mix them up.

### 4.4. `fail` and `InvocationTargetException`

The `fail()` method on the backend throws `IllegalStateException("boom")`. `Method.invoke(target, args)` will wrap the exception thrown by the target method in an **`InvocationTargetException`**.

The handler catches this wrapper and rethrows **the original cause**:

```java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException exception) {
    throw exception.getCause();
}
```

Thanks to this, the client catches the exact `IllegalStateException` and prints `caught=boom`. If the handler throws `InvocationTargetException` directly, which is a checked exception not declared by the interface method, the dynamic proxy may wrap it further in `UndeclaredThrowableException`. Returning the original cause preserves the exception contract of the target method, while still having to obey the interface's `throws` clause for checked exceptions.

### 4.5. `toString`, `equals`, `hashCode` and `sameObject`

JDK dynamic proxies forward calls to `equals(Object)`, `hashCode()`, and `toString()` to the handler, with `Method.getDeclaringClass()` being `Object.class`, even if these methods are not written directly in the interface.

The example defines an **identity semantics** policy for the proxy:

- `equals`: true only when the argument `== proxy`.
- `hashCode`: uses `System.identityHashCode(proxy)`.
- `toString`: returns a stable label `"ServiceProxy"`.

Therefore `equalsSelf=true`, `equalsTarget=false`, `hashIdentity=true`. And `sameObject=false` because `service` and `real` are **two separate objects**; the proxy *represents* the target rather than being the target.

If an application wants value equality or wants multiple proxies representing the same target to be considered equal, a different consistent `equals/hashCode` policy is needed. **Do not arbitrarily choose** `equals` by proxy identity but `hashCode` by target, or vice versa: that violates the contract that two equal objects must have the same hash code.

### 4.6. Demonstrating a terminating error without causing a real StackOverflow

`LoopingHandler` intentionally calls `method.invoke(proxy, args)` to reproduce the anti-pattern. However, the example uses a `calls` variable and throws `IllegalStateException("proxy re-entered")` when exceeding the threshold.

This demonstrates the loop and prints `recursionDetected=proxy re-entered` **safely**. The counter in this handler is **for single-threaded demo purposes only**, not a production recursion detector: it does not reset per call chain, is not safe under concurrent use, and will reject subsequent calls after exceeding the threshold. In a real system, **fix the source of the cycle** rather than just placing an arbitrary counter.

## 5. Distinguishing infinite recursion, nested calls, and self-invocation bypass

Three situations may look similar in logs, but their natures are different:

| Situation | Call chain | Is it a bug? | How to handle |
| --- | --- | --- | --- |
| **Proper delegation** | `proxy.work` → handler → `target.work` | No | Standard approach when the backend implements the interface |
| **Direct loop** | `proxy.work` → handler → `proxy.work` → handler → ... | Yes | Do not use `proxy` as the receiver when delegating |
| **Indirect loop** | proxy A → handler A → proxy B → handler B → proxy A → ... | Yes | Inspect the delegation graph, remove the cycle |
| **Valid reentrancy** | proxy.defaultMethod → handler → default body on proxy → proxy.otherMethod → handler → target | No if properly terminating | Allow intentional nested calls |
| **Self-invocation bypass** | proxy.outer → handler → target.outer → `this.inner` on target | Not necessarily; but may miss interceptors | Adjust architecture if interception of `inner` is needed |

Therefore, a rule like "a handler must not appear twice in the same call stack" **is not generally true**. What needs to be ensured is that the execution path has a reasonable stopping point and calls are forwarded to **the right receiver** per the contract.

If there are multiple proxy layers, you can draw a call graph per configured method and target:

```text
Client -> LoggingProxy -> SecurityProxy -> RealService   [terminates]

Client -> ProxyA -> ProxyB -> ProxyA                    [cycle]
```

In real systems, auditing the chain when constructing objects is more effective than waiting for a stack overflow to investigate. Configured objects must be distinguished by **identity**, not just class name, because two proxies of the same generated class can carry two different handlers.

## 6. Safe delegation technique: holding a validated target

In a production handler, you should receive `target` from a constructor or controlled factory, store an explicit reference, and verify that it implements the interface.

For example, a factory concept:

```java
static <T> T wrap(Class<T> api, T target, InvocationHandler handler) {
    if (!api.isInterface()) {
        throw new IllegalArgumentException("API must be an interface");
    }
    if (!api.isInstance(target)) {
        throw new IllegalArgumentException("Target does not implement API");
    }
    Object proxy = Proxy.newProxyInstance(
            api.getClassLoader(), new Class<?>[] { api }, handler);
    return api.cast(proxy);
}
```

**The snippet above is a standalone illustration**: it needs imports for `Proxy`, `InvocationHandler`, and must ensure that the passed `handler` itself holds/is connected to `target`. If `handler` uses a completely different target, checking the `target` variable in the factory does not guarantee proper delegation. A real factory design should create the handler itself with the validated target to avoid configuration mismatch.

Good approach:

1. Clearly define **the proxied interface** and **the target that the handler actually calls**.
2. Keep the target as a separate dependency; do not use the `proxy` parameter as the backend.
3. Ensure the target does not point back to the proxy itself or an unintended cyclic proxy chain.
4. For regular methods, use `method.invoke(target, args)` when the target is compatible with the declared method.
5. For `Object` methods or default methods, choose a separate policy and document it as a contract.
6. Translate Reflection exceptions into appropriate business exceptions.
7. Use tests to verify the number of times the target is called and that the handler terminates.

Do not assume that the target must be a non-proxied concrete class. A proxy chain can be valid in frameworks. The issue is **ownership, mapping, and delegation chain structure**, not simply `Proxy.isProxyClass(target.getClass())`.

## 7. Handling `args` and exact method signatures

`InvocationHandler.invoke` receives `Object[] args`, or `null` if the method has no parameters. Several common mistakes:

### 7.1. Passing `args` properly

```java
return method.invoke(target, args);
```

In Java, this is a varargs call directly receiving the `Object[] args` array; when `args == null` for a parameterless method, `Method.invoke` accepts it per the API contract.

Do not replace it with:

```java
return method.invoke(target, new Object[] { args }); // EASILY WRONG
```

The second line turns **the entire old array** into **a single argument**. If the target method takes two parameters `(int, String)`, the result will be a wrong number/type of arguments (`IllegalArgumentException`). Only use single-layer wrapping if the target method actually takes **one array-typed parameter** and you intentionally want to pass the whole array as a single value.

### 7.2. Overloaded methods

Suppose the backend has two methods:

```java
String send(String data);
String send(Object data);
```

These are two **illustrative** declarations in a corresponding class/interface. Comparing only `method.getName().equals("send")` is not enough to know which overload was called. `Method` contains parameter types, return type, and declaring class. With a target implementing the interface, using the `Method` metadata received by the handler directly (when valid) helps avoid picking the wrong method yourself.

If you need to map an interface method to a different backend method, use `method.getParameterTypes()` and the full signature to look up the target method, rather than searching by name and taking the first element of `getMethods()`.

### 7.3. Return values

The handler returns an `Object`:

- Interface method `String foo()` → returns `String` or `null` when the contract allows.
- Interface method `void foo()` → returning `null` is appropriate.
- Interface method `int count()` → returns an appropriate `Integer` wrapper; if returning `null`, the generated proxy may throw `NullPointerException` when unboxing.
- Returning an object of the wrong type for a reference-returning method can cause `ClassCastException`.

`Method.invoke` normally auto-boxes a primitive result into a wrapper in the `Object` value returned to the handler, so forwarding the result directly is usually appropriate. If the handler modifies the return value (caching, masking data, default), it must strictly obey the interface contract.

## 8. `InvocationTargetException` and checked exceptions through a proxy

Reflection distinguishes two groups of errors:

1. **The target method executes and throws an exception** → `Method.invoke` wraps the error in an `InvocationTargetException`.
2. **Reflection cannot execute the call** (wrong receiver, wrong arguments, access denied) → Reflection's own error, e.g., `IllegalArgumentException` or `IllegalAccessException`.

A good forwarding handler only unwraps **`InvocationTargetException`** when it needs to propagate the target's exception outward, and handles wiring/access errors separately. Do not catch every `Throwable` and ignore it: it can lose track of serious errors and hide recursion.

`InvocationHandler.invoke` declares `throws Throwable`, but **the interface's proxy method still has its own throws clause**. If the handler throws a **checked exception not declared by the interface method** (and not a valid subtype), the generated proxy will wrap it in `UndeclaredThrowableException`.

### 8.1. Second Java 17+ example: declared and undeclared checked exceptions

Save as a standalone file **`ProxyExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class ProxyExceptionDemo {
    interface Task {
        void declared() throws IOException;
        void undeclared();
    }

    public static void main(String[] args) {
        Task task = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, values) -> {
                    throw new IOException("disk");
                });

        try {
            task.declared();
        } catch (IOException ex) {
            System.out.println("declared=" + ex.getMessage());
        }

        try {
            task.undeclared();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("wrapped="
                    + ex.getUndeclaredThrowable()
                            .getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac --release 17 ProxyExceptionDemo.java
java ProxyExceptionDemo
```

Verified output:

```text
declared=disk
wrapped=IOException
```

`Task.declared()` allows `IOException`, so the checked exception is passed straight to the caller. `Task.undeclared()` does not allow checked `IOException`, so the proxy wraps it in `UndeclaredThrowableException`. In this example the handler throws `IOException` itself; with a handler delegating via Reflection, **unwrapping the cause from `InvocationTargetException` first** allows the original exception to be handled properly according to the throws clause.

Do not declare `throws Throwable` on every interface method just to dodge contract checking. Define a clear exception contract, and when mapping an internal exception to another public exception, preserve the cause for debugging.

## 9. `equals`, `hashCode`, `toString`: calls that easily cause unexpected reentrancy

A dynamic proxy handles the three public methods of `Object`—`equals`, `hashCode`, and `toString`—through `InvocationHandler`, even if the interface does not list them. Therefore, a seemingly harmless log statement can cause a loop:

```java
System.out.println("proxy=" + proxy);
```

**This standalone illustrative snippet is dangerous when placed inside a handler.** String concatenation with `proxy` can call `proxy.toString()`, then `toString()` enters the handler again, the handler logs `proxy` again, and so on.

A safer way to identify the proxy in logs is to use information that does not invoke virtual methods on the proxy, for example:

```java
System.out.println("proxyIdentity="
        + System.identityHashCode(proxy));
```

`System.identityHashCode(proxy)` does not call `proxy.hashCode()` through the handler, thus helping avoid logging-induced cycles. Do not infer that `identityHashCode` is a globally unique ID; hashes can collide and are not suitable as a security identifier.

For `equals`:

- Avoid `proxy.equals(other)` right inside the proxy's own `equals` handling.
- If identity comparison is needed, use `proxy == other`.
- If the equality policy is target-based, decide how to compare the proxy with the target, with other proxies, and across decorator chains; it must obey the reflexive/symmetric/transitive contract of `equals`.

For `hashCode`:

- Hash must be consistent with the `equals` policy.
- If using identity semantics on the proxy, `System.identityHashCode(proxy)` is simple and non-recursive.

For `toString`:

- Use a fixed descriptive string or determined metadata.
- Avoid calling `proxy.toString()` again from the handler.
- Do not log sensitive target information just because the proxy is an intermediary layer.

**Another pitfall:** checking the method by `method.getDeclaringClass() == Object.class` for these three methods is clear. If an interface also declares methods matching `Object`'s `equals(Object)`, `hashCode()`, `toString()`, the JDK still prioritizes the method with declaring class `Object.class` when dispatching to the handler.

## 10. Default methods: choosing clearly between two delegation strategies

Since Java 8, interfaces can contain `default` methods. With dynamic proxies, there are two choices to distinguish:

### Strategy A — run the default method on the target

If the target implements the interface and does not override the default method, `method.invoke(target, args)` will execute the default implementation **with the target as the receiver**. Calls to `this.otherMethod()` inside the default method will go through the target receiver and may **bypass the proxy**. This approach makes sense when you want the proxy to intercept only external calls and let the backend handle internal logic naturally.

### Strategy B — run the default method on the proxy using `InvocationHandler.invokeDefault`

If the handler uses:

```java
return InvocationHandler.invokeDefault(proxy, method, args);
```

and `method` is indeed a valid default method of a proxy interface, the default implementation is invoked as `Interface.super.method(...)` **on the proxy**. Subsequent calls to other interface methods from the default body can go back into the handler and be subject to interceptors.

This is **intentional reentrancy** rather than repeating the same default method via `Method.invoke(proxy, args)`. `InvocationHandler.invokeDefault` **is not equivalent** to `method.invoke(proxy, args)`.

`invokeDefault` requires the method to be a valid default method for the proxy interface hierarchy. With complex interface inheritance, overridden default methods, or wrong method selection, the API may throw `IllegalArgumentException`/`IllegalAccessException` accordingly. Only call it after verifying `method.isDefault()` and a suitable interface structure.

**Neither choice is always better:** choosing the target or the proxy as the receiver for a default method changes the scope of intercepted calls. Do not apply it mechanically when a framework also has AOP, transactions, or permission checks that depend on the proxy entrypoint.

## 11. Self-invocation bypass: a quirk easily mistaken for a recursion bug

Consider the code in `RealService`:

```java
public String outer(String input) {
    return "outer(" + inner(input) + ")";
}
```

When the client calls `proxy.outer(...)`, the handler only sees the `outer` call and forwards it to `target.outer(...)`. The `inner(...)` call inside the target is equivalent to `this.inner(...)`, so it directly invokes the target's method, **without going through the proxy**.

If the handler is:

- Logging each method;
- Opening a transaction at the entrypoint;
- Authenticating/authorizing before an operation;
- Collecting metrics or applying caching;

then this self-invocation may skip the interceptor behavior on `inner`, even when both methods are public and interface members.

This is a **consequence of the proxy model**, and cannot be solved by keeping `target.outer(...)` as-is while expecting Java to automatically rewrite every `this` to `proxy`. Standard Java does not do that.

Design options depending on needs:

1. **Extract a collaborator:** move the part needing interception to another service that the target calls through an interface/proxy.
2. **Orchestrate at the calling layer:** instead of `outer` calling `inner` itself, the controller/application service calls operations through the proxy in the desired order.
3. **Controlled proxy reference injection:** if the framework supports it, allow the implementation to reference its own proxy to call *another method*; must prove it creates no direct/indirect cycle, avoiding circular dependency.
4. **Use interception not solely based on proxy entrypoints:** e.g., bytecode weaving in an appropriate framework, if the requirement truly is to intercept self-invocations as well.

Do not confuse valid nested calls with buggy recursion. A default method running on a proxy can intentionally call another method through the handler; the buggy part is when the handler **delegates the very method being handled** back to **the same proxy**.

## 12. Proxy chains and indirect reference cycles

A real system may have multiple layers:

```text
Client
  -> LoggingProxy
      -> AuthorizationProxy
          -> RetryProxy
              -> RealService
```

This is a valid chain if the handlers are clearly configured and each step moves toward the final target. However:

```text
LoggingProxy
  -> AuthorizationProxy
      -> LoggingProxy
          -> ...
```

is a cycle. Even though each individual handler uses a variable named `target`, the target configuration can point in a circle.

**Checking the architecture before running** is a better measure than putting a global depth counter to "cure" all recursion. If a guard is needed in a dynamically configured system, design it clearly:

- Guard by **call chain** or **operation id**, not by application-wide call count.
- Use `try/finally` to release state.
- Consider multithreading, async delegation, thread pools, and context propagation.
- Do not block valid business recursion just because the same method name appears again with different arguments.
- Report cycles with configuration names/object identity without accidentally calling `toString` on the proxy.

A `ThreadLocal` guard can be useful in some synchronous cases, but **does not automatically solve** calls across threads, async tasks, or virtual-thread contexts. Do not treat it as a substitute for an acyclic graph design.

## 13. Why should you not log `proxy` or call `toString` arbitrarily?

A common handler:

```java
System.out.printf("Intercepted %s on %s%n", method, proxy);
```

**This is an anti-example** if `proxy` is formatted using `toString()`. When the client method is `toString`, the logging behavior itself generates another `toString`. It can create a loop even when the business delegation part of the handler is correct.

Log safer information:

```java
System.out.printf("method=%s proxyId=%d%n",
        method.getName(), System.identityHashCode(proxy));
```

The snippet above is only an illustration using the handler's `method` and `proxy` variables, not a standalone program. You can print `method.getDeclaringClass().getName()` or the interface name when overload analysis is needed; be careful with sensitive information and log length.

For `target`, if calling `target.toString()` in logs, also consider what it might do: a target could be another proxy, and its `toString` method might access sensitive data or re-enter the chain. **Logging is also execution behavior**, not pure observation.

## 14. Testing handlers: don't just check the return value

A proxy can return the right value while still calling the target twice or looping part of a chain. Tests should observe **the execution path**, not just the output.

### 14.1. Minimum test cases

| Case | What to verify |
| --- | --- |
| Value-returning method | Real target is called exactly once per external call |
| `void` method | Handler handles `null` return properly |
| Parameterless method | `args` can be `null`, causes no error in Reflection call |
| Overloaded method | Selects right metadata/signature, does not mix overloads |
| Method throwing runtime exception | Handler unwraps `InvocationTargetException`, caller sees original error |
| Method throwing checked exception | Respects `throws` clause; understands `UndeclaredThrowableException` |
| `equals/hashCode/toString` | No reentrancy from handler/log, consistent equality contract |
| Default method | Verifies running on proxy or target as intended |
| Target self-invocation | Verifies whether internal methods need interception |
| Proxy chain | No reference cycles between handlers |
| Concurrent requests | Handler state, metrics, and cache are handled thread-safely |
| Null/primitive return | Obeys return type and boxing/unboxing rules |

A good test example can use a target test double that increments an `AtomicInteger` in `work` and checks the count after the proxy call. For recursion scenarios, use a handler with a **clear stopping point** as in section 4 rather than intentionally running into an infinite loop and relying on `StackOverflowError`.

### 14.2. When the recursion bug only occurs in `toString`

If `work(...)` works but `System.out.println(proxy)` fails, check:

1. Does the handler concatenate/log `proxy` directly?
2. Does the `Object.toString` handling branch call `proxy.toString()` again?
3. Is the target another proxy whose `toString()` points back to the current proxy?
4. Does the framework's equality/hash code call a getter or service method that goes back through the proxy?

Do not fix only `work(...)`; looping through `Object` methods is an independent bug path.

### 14.3. When errors appear as multi-layered wrapped exceptions

If the stack trace has multiple `InvocationTargetException` or `UndeclaredThrowableException` layers, check what the handler is throwing. An `InvocationTargetException` propagated through a proxy method that does not declare checked exceptions can be wrapped. However, you should **not** try to unwrap all exceptions in a loop regardless of context; framework layers may have their own contracts. For a direct delegating handler, unwrapping **the exact `InvocationTargetException` just thrown by `method.invoke(target,args)`** is the clearest principle.

Also look for a repeating `Proxy...invoke → handler.invoke → Method.invoke → Proxy...invoke` sequence in the stack trace; that is a sign the receiver may be the proxy instead of the target.

## 15. Common errors and fixes table

| Common error | Cause | Fix |
| --- | --- | --- |
| `StackOverflowError` when calling method via proxy | Handler calls `method.invoke(proxy,args)` or proxy chain forms a cycle | Delegate to real backend; fix the chain |
| Handler called repeatedly when logging | Logging `proxy` triggers `toString` via handler | Log method name and `System.identityHashCode(proxy)` |
| `IllegalArgumentException: object is not an instance of declaring class` | `Method.invoke` receives an incompatible receiver | Ensure target implements the interface or map the method properly |
| `InvocationTargetException` leaks to caller | Handler does not unwrap target's error | `catch (InvocationTargetException e) { throw e.getCause(); }` |
| `UndeclaredThrowableException` | Handler throws checked exception not declared by interface | Obey contract, convert to appropriate exception or change interface |
| `inner` call inside `outer` not intercepted | `this.inner` runs directly on target | Extract service or orchestrate via proxy if needed |
| Default method does not produce expected nested interceptor call | Default method runs on target instead of proxy | Consider `InvocationHandler.invokeDefault` when appropriate to contract |
| `equals` always false or `hashCode` inconsistent | Mixing target equality and proxy identity | Choose a clear and consistent policy |
| `NullPointerException` when method returns primitive | Handler returns `null` for `int`/`boolean` method | Return right wrapper type or handle contract |
| `IllegalArgumentException` due to argument count | Inappropriately wrapping `args` into `new Object[]{args}` | Pass `args` directly if method takes the original parameters |
| Interceptor runs twice unintentionally | Some target calls go into another proxy or self-delegation | Trace call graph and define ownership |

**Do not catch `StackOverflowError` as a strategy to avoid recursion in production.** This error can leave the environment in an unsafe state to continue processing. Prevent loops with the right receiver/graph and bounded tests from the start.

## 16. Process for designing a proper forwarding `InvocationHandler`

An auditable approach:

1. **Choose the interface** as the public contract for the proxy; identify which methods need interception.
2. **Create the backend** of the right type and keep a separate reference in the handler; do not use the `proxy` parameter as the backend.
3. **Define the policy** for `Object` methods first, especially how `equals/hashCode/toString` interact with the target.
4. **Define default methods**: run on the proxy with `invokeDefault` or on the target with Reflection? Choose an intentional strategy.
5. **Forward regular methods to the target** with `method.invoke(target,args)` after ensuring compatible receiver and signature.
6. **Unwrap target errors** from `InvocationTargetException` and obey the interface's `throws` clause.
7. **Draw the proxy chain** if there are multiple handlers/decorators; confirm there is no path back to the calling proxy.
8. **Test valid reentrancy** (default method calling another method) and self-invocation bypass; do not apply an overly broad depth guard.
9. **Test concurrency and side effects** if the handler holds mutable state (counters, cache, tracing context, auth context).
10. **Keep observability non-reentrant**: do not unconditionally print the entire proxy/target inside the handler; use smart metadata/identity.

If you only need a static decorator for a simple interface, sometimes a hand-written wrapper class is easier to understand, debug, and maintain than a dynamic proxy. `Proxy` is suitable when you need general interception across many interface methods without writing repetitive boilerplate.

## 17. Self-check questions

1. In `InvocationHandler.invoke(proxy, method, args)`, is `proxy` the real target? **No.** It is the proxy object that the client called.
2. Why does `method.invoke(proxy,args)` easily cause infinite recursion? **Because it calls the method on the proxy again, causing the JVM to dispatch into the handler once more.**
3. Is `method.invoke(target,args)` always right for any `target` object? **No.** The receiver must be compatible with the declared method and the delegation graph must terminate.
4. Is Proxy A forwarding to Proxy B and Proxy B forwarding to the real target wrong? **Not necessarily.** That can be a valid decorator chain.
5. What if Proxy A forwards to Proxy B and Proxy B goes back to Proxy A? **Creates an indirect cycle**, even though neither handler calls its own proxy directly.
6. Why doesn't `RealService.outer` calling `inner` produce an extra `log:inner`? **Because `this` is the target, not the proxy.**
7. Why does `decorated` in the example produce an extra `log:work`? **Because `invokeDefault` runs the default method on the proxy and `work(...)` inside it calls back through the proxy.**
8. Should every handler re-entry be blocked? **No.** Nested calls to different methods can be completely valid.
9. Is `InvocationTargetException` the original business exception from the target? **No.** It is a Reflection wrapper; get the cause to propagate the original error.
10. Why does `UndeclaredThrowableException` happen? **Because the handler threw a checked exception incompatible with the interface method's `throws` clause.**
11. Why can `System.out.println(proxy)` cause recursion? **Because it can call `proxy.toString()`, which is also intercepted.**
12. What should be used to log proxy identity without calling `proxy.hashCode()`? **`System.identityHashCode(proxy)`**, while recognizing that hash numbers are not strictly unique.
13. Is `args == null` always an error? **No.** It is the valid case when the interface method has no arguments.
14. If an interface has two overloads with the same name, should you select the method by name? **No.** You must inspect parameter types/signature.
15. Can an `InvocationHandler` run a default method on a proxy in Java 17? **Yes**, with `InvocationHandler.invokeDefault` if the method is valid.
16. Are `equals(proxy)` and `hashCode()` automatically forwarded to the target? **No.** They go to the handler, and the handler must decide the policy.
17. Should a loop be allowed to run until `StackOverflowError` in unit tests? **No.** Use a safe stopping point or controlled configuration.
18. What is the most important thing to avoid delegation-induced recursion? **Ensure the handler calls the right receiver (the real target) and the graph of proxy layers has no unintended cycles.**

## 18. Official documentation for reference

- [Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): how dynamic proxies are created, interface method dispatch, and the special case of `Object.equals/hashCode/toString`.
- [Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): meaning of `proxy`, `method`, `args`, exception rules, and `invokeDefault`.
- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): receiver, arguments, `InvocationTargetException`, and dynamic lookup of instance methods.
- [Java SE 17 — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): checked exceptions not in the `throws` clause when passing through a proxy.

**Summary:** `InvocationHandler` must distinguish **`proxy` for receiving and dispatching** from **`target` for executing business logic**. Avoid `method.invoke(proxy,args)` when you want to delegate regular methods; use `method.invoke(target,args)`, unwrap Reflection exceptions, and separately define policies for `Object`/default methods. Keep proxy chains acyclic, allow valid reentrancy, and test execution paths to avoid both infinite recursion and unintended interception bypass.