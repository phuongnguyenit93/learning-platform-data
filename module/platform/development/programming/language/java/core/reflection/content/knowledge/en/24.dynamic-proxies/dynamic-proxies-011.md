# Avoiding Calling Back Into the Proxy That Causes Infinite Recursion in Java Dynamic Proxies

## 1. Objective and context

When using a **JDK Dynamic Proxy**, every method call on the proxy is routed to `InvocationHandler.invoke(...)`. A common mistake is that inside the handler, a developer invokes the method **on the proxy object itself** to "execute the original method." That call triggers the handler again; the loop can continue until the call stack is exhausted and `StackOverflowError` occurs.

After this lesson, you will be able to:

- Distinguish `proxy` (the intermediary object) from `target` (the real implementation object).
- Recognize direct recursion via `method.invoke(proxy, args)` and indirect recursion via logging, `toString()`, `equals()`, or `hashCode()`.
- Properly forward calls to `target`, handle reflective exceptions, and handle `Object` methods.
- Understand when calling back into a proxy is **intentional** and when it creates an unwanted cycle.

This article focuses on **JDK Dynamic Proxy** (`java.lang.reflect.Proxy`), which creates proxies for **interfaces**. Subclass-based proxy mechanisms from other libraries may differ in how they forward calls.

## 2. Mechanism that causes recursion

A handler is declared according to the `InvocationHandler` interface:

```java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
```

Where:

- `proxy` is **the proxy object itself** that the caller just used, not the real business object.
- `method` describes the method the caller requested; it may be an interface method or `equals`, `hashCode`, `toString` from `Object`.
- `args` contains the call's arguments; may be `null` if the method has no parameters.

**Wrong example**, merely a code fragment placed in a context where `InvocationHandler` is imported:

```java
InvocationHandler badHandler = (proxy, method, args) -> {
    System.out.println("Call " + method.getName());
    return method.invoke(proxy, args); // WRONG: calls back into the proxy itself
};
```

If a client calls `service.greet("An")`, the execution flow becomes:

```text
client calls proxy.greet("An")
    -> InvocationHandler.invoke(proxy, greet, ["An"])
       -> method.invoke(proxy, ["An"])
          -> InvocationHandler.invoke(proxy, greet, ["An"])
             -> method.invoke(proxy, ["An"])
                -> ... repeats ...
```

`Method.invoke(...)` does not "bypass" the handler when the receiver is a proxy. It is still a call to a method on the proxy, so the dispatch mechanism activates again. The outcome is typically `StackOverflowError`; the stack trace may alternate between proxy methods, the handler, and Java Reflection. **Do not run the wrong snippet as a stress test**, because overflowing the stack provides no additional learning value.

Core rule: **`proxy` is the entry point receiving calls; `target` is where the work happens if you are building a delegating proxy.**

## 3. How to fix: forward to the real object

When a proxy is used for timing, logging, permission checks, or adding behavior around an existing object, the right structure is:

```text
caller -> proxy -> InvocationHandler
                       |
                       +-> log / validate
                       +-> method.invoke(target, args)
                       +-> return result to caller
```

Make sure that:

1. `target` is an object **distinct from the proxy**, implementing the interface containing the invoked method.
2. The handler uses `method.invoke(target, args)` instead of `method.invoke(proxy, args)`.
3. If an operation on `target` calls back into the proxy, inspect the actual call flow to eliminate **cyclic dependencies**. Simply replacing the receiver with `target` does not automatically resolve every indirect cycle.

### Standalone runnable Java 17+ program

Create the file `SafeProxyDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class SafeProxyDemo {
    public interface GreetingService {
        String greet(String name);
    }

    static final class RealGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    public static void main(String[] args) {
        GreetingService target = new RealGreetingService();

        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == arguments[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "GreetingProxy@" +
                            Integer.toHexString(System.identityHashCode(proxy));
                    default -> throw new UnsupportedOperationException(method.getName());
                };
            }

            System.out.println("Calling: " + method.getName());
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException e) {
                throw e.getCause();
            }
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] { GreetingService.class },
                handler);

        System.out.println(service.greet("An"));
        System.out.println(service.toString().startsWith("GreetingProxy@"));
        System.out.println(service.equals(service));
        System.out.println(service.hashCode() == System.identityHashCode(service));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac SafeProxyDemo.java
java SafeProxyDemo
```

Output (this program was run to verify):

```text
Calling: greet
Hello, An!
true
true
true
```

**Explanation:**

- `target` is `RealGreetingService` and actually handles `greet`.
- The handler logs the method name using `method.getName()`; reading this metadata does not call back into the proxy.
- `method.invoke(target, arguments)` executes the method on `target`. The result returns through the handler to the client without creating a loop.
- The last three checks verify the behavior of `toString`, `equals`, and `hashCode`. `toString()` is genuinely called on the proxy, but the `Object` branch returns a synthesized string **without calling** `proxy.toString()` again.
- `System.identityHashCode(proxy)` obtains the identity hash code directly without calling `proxy.hashCode()`.
- `InvocationTargetException` wraps exceptions thrown by the target method; `throw e.getCause()` propagates the root cause through `InvocationHandler`. Proxy forwarding of checked exceptions still adheres to the interface's `throws` declaration.

The example uses **proxy identity** equality to ensure `service.equals(service)` is `true`. This is a deliberate choice: if the application requires business-based equality, design both `equals` and `hashCode` consistently rather than delegating arbitrarily.

## 4. Indirect trap: logging can also call back into the proxy

Even when already using `method.invoke(target, args)`, a handler can still trigger self-recursion:

```java
// Code fragment illustrating a bug inside a handler.
System.out.println("Proxy: " + proxy); // WRONG in a general handler
return method.invoke(target, args);
```

The string concatenation operator converts `proxy` into a string, invoking `proxy.toString()`. With a JDK dynamic proxy, `toString()` also goes through `InvocationHandler`. The new call runs that exact same logging line, then calls `toString()` again.

Cases to distinguish:

| Expression inside handler | Can it re-invoke handler? | Alternative or note |
| --- | --- | --- |
| `method.invoke(proxy, args)` | **Yes**, for proxy-dispatched methods | Forward to the real `target` if delegating |
| `proxy.toString()`, `"proxy=" + proxy`, `System.out.println(proxy)` | **Yes**, via `toString` | Log `method.getName()` or `System.identityHashCode(proxy)` |
| `proxy.hashCode()` | **Yes**, via `hashCode` | Use `System.identityHashCode(proxy)` when identity is needed |
| `proxy.equals(other)` | **Yes**, via `equals` | Use `proxy == other` if reference comparison is intended |
| `proxy.getClass()` | **No** for normal `Object.getClass()` calls | `getClass` is `final`, not overridden to dispatch to handler |
| `method.getName()`, `method.getDeclaringClass()` | **No** | Only reads `Method` metadata |

Do not write `logger.info("proxy={}", proxy)` and assume placeholder-based logging avoids calling `toString()`. Many loggers format objects when emitting the log; calling `toString()` can still happen afterward. When debugging a handler, prefer a fixed label, method name, and identity hash.

## 5. Why must Object methods be handled carefully?

On a JDK dynamic proxy, calls to `equals(Object)`, `hashCode()`, and `toString()` are sent to `InvocationHandler`. Therefore, a handler that only knows how to call `method.invoke(target, args)` can cause **semantic errors** even without overflowing the stack.

For example, if `target` uses the default `Object.equals`, forwarding `proxy.equals(proxy)` into `target.equals(proxy)` can return `false`. That violates the reflexivity property of `equals` (`x.equals(x) == true`). Similarly, `proxy.hashCode()` might return the target's hash code while `equals` is defined by proxy identity, breaking `equals/hashCode` consistency if overlooked.

A safe handling approach for identity-based proxies is:

```java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "equals" -> proxy == args[0];
        case "hashCode" -> System.identityHashCode(proxy);
        case "toString" -> "ServiceProxy@" +
                Integer.toHexString(System.identityHashCode(proxy));
        default -> throw new UnsupportedOperationException(method.getName());
    };
}
```

This is a code fragment inside `invoke`; `args[0]` is used in the single-parameter `equals(Object)` branch. If the interface has special identity or equality requirements, change this policy intentionally and test it.

## 6. Distinguishing unintended recursion from valid nested calls

Not every re-entry into `InvocationHandler.invoke` is a bug. For instance, when implementing an interface's default method, that method may call another method on `this`, and the second call is valid as long as it eventually terminates.

In Java 17, the `InvocationHandler.invokeDefault(proxy, method, args)` API allows invoking the default implementation of an interface method **without calling back into the handler to execute that default method itself**:

```java
// Code fragment inside InvocationHandler.invoke(...), used when appropriate:
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

Note that **the default method body can still call other methods on the proxy**. If those calls loop back to the same default method without a termination condition, a cycle still exists. `invokeDefault` is not a general recursion-prevention mechanism.

Similarly, a proxy can wrap another proxy to form a valid interceptor chain. What must be eliminated is a **call cycle** such as `proxyA -> handlerA -> proxyB -> handlerB -> proxyA`, not all nested calls.

## 7. Diagnosing and fixing StackOverflowError

When seeing `StackOverflowError` during dynamic proxy invocation:

1. **Read the repeating frame sequence** in the stack trace. Look for frames of `InvocationHandler.invoke`, `Method.invoke`, the proxy class, and logging functions. This sequence reveals which call loops back to the starting point.
2. **Find every use of `proxy` inside the handler**, especially method call receivers, string conversions, and callbacks executed by the target. Do not search only for the exact line `method.invoke(proxy, args)`.
3. **Identify the real call receiver**: if the handler is designed to delegate, `target` must implement the target interface and must not point back to the newly created proxy. If using multiple proxy layers, draw the layer order to spot cycles.
4. **Fix the call path**: invoke the real target, provide explicit handling for `Object`, or use the dedicated default-method API when appropriate.
5. **Test behavior**: invoke a business method, `toString`, `equals`, `hashCode`, a zero-parameter case, an exception-throwing path, and a target wrapped by multiple interceptors if the application uses them.

A re-entry guard such as `ThreadLocal<Boolean>` can be useful when the application **intentionally forbids** a thread from entering the handler a second time; the state must be cleared in `finally`. However, placing a blanket guard on all nested calls can reject valid interactions between methods. The primary fix remains redesigning the forwarding path so it forms no cycles.

Do not try to "fix" it by increasing stack size (`-Xss`) or catching and ignoring `StackOverflowError`. Those do not fix the broken call flow and can cause the application to fail in harder-to-trace ways.

## 8. Common mistakes and self-check exercises

**Common mistakes:**

- Accidentally using `proxy` instead of `target` as the receiver of `Method.invoke`.
- Logging the raw proxy inside the handler and inadvertently triggering `toString`.
- Ignoring `equals/hashCode/toString` or forwarding them to the target without checking object contracts.
- Holding a reference to the proxy as the target when configuring multiple interceptors.
- Wrapping `InvocationTargetException` again without checking the root cause; this makes diagnosing real business-method exceptions harder.
- Treating every nested call as an error and adding an overly broad re-entry block.

**Self-check:**

1. Why can `method.invoke(proxy, args)` call `InvocationHandler.invoke` again? Because the receiver is still the proxy, so the call is dispatched through the handler.
2. If a handler prints `"Processing: " + proxy`, what can happen? String concatenation calls the proxy's `toString`, usually triggering that same handler.
3. How do you obtain an identity hash code for logging without going through the proxy's `hashCode`? Use `System.identityHashCode(proxy)`.
4. When is `method.invoke(target, args)` still unsafe? When `target` is itself that proxy, forms a cycle through other proxies, or the target calls back into the proxy infinitely.
5. Does `InvocationHandler.invokeDefault` guarantee no loops remain? No; it only calls the default method body directly, while that body can issue other calls and form a cycle.

**Takeaway:** Inside `InvocationHandler`, the `proxy` variable represents the entry point of the intercepted call. To delegate, invoke **the real target object** and control indirect call paths, especially logging and the three methods `equals/hashCode/toString`.