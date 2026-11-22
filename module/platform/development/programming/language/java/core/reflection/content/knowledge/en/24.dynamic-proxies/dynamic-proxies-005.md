# Calls Through a Dynamic Proxy Are Dispatched to `InvocationHandler.invoke`

## 1. Meaning of the call forwarding mechanism

With **JDK dynamic proxy** (`java.lang.reflect.Proxy`), an application creates an object at runtime implementing one or more **interfaces**. When code invokes a method through an interface on the proxy object, the JDK-generated proxy class routes the call to `InvocationHandler.invoke(proxy, method, args)`. The handler decides what to do: return a result directly, invoke a real object (*target*), check permissions, log, measure time, or throw an exception.

The core point of this article is that **calling a method on a proxy triggers the handler; it does not automatically run the same-named method of a target object**. Only when the handler explicitly invokes the target does the target's business logic run.

Example path:

```text
Caller
  |
  | service.greet("Lan")  // service is a JDK proxy
  v
Method greet in the JDK-generated proxy class
  |
  | handler.invoke(proxy, Method(greet), Object[]{"Lan"})
  v
InvocationHandler
  |-- handle directly and return String
  |-- or check/log then call method.invoke(target, args)
  |-- or throw an exception
  v
Return value / exception is passed back to caller
```

The interface itself only defines the contract, such as `GreetingService.greet(String)`; the proxy provides an implementation at runtime through the handler. This is useful when you want to insert shared behavior around many calls without changing how interface-consuming code makes those calls.

## 2. Creating a proxy object and conditions for use

API-level proxy creation example:

```java
GreetingService service = (GreetingService) Proxy.newProxyInstance(
    GreetingService.class.getClassLoader(),
    new Class<?>[] { GreetingService.class },
    handler
);
```

This is an **illustrative snippet**, assuming `GreetingService` and `handler` are already defined. The three arguments serve these roles:

1. **Class loader:** used to define the proxy class and resolve the requested interfaces; the loader must match interface visibility requirements.
2. **Interface array:** the set of interfaces the proxy implements. Calls through these interfaces are routed to the handler. The interfaces must satisfy API validity conditions (for example, being interfaces and having no duplicates).
3. **`InvocationHandler`:** the object that processes forwarded calls.

`Proxy.newProxyInstance(...)` returns `Object`, so casting to an interface is usually needed. The proxy's class is a runtime-generated class extending `Proxy` and implementing the specified interfaces. JDK `Proxy` **does not automatically create a subclass of any concrete class**; if you need to override the behavior of a concrete class, you must choose another suitable mechanism.

From the calling code's perspective, the syntax looks normal:

```java
String message = service.greet("Lan");
```

Even though the caller invokes it like an ordinary Java method, because `service` is a proxy, that call enters the handler.

## 3. Four parts of `InvocationHandler.invoke`

The `InvocationHandler` interface declares:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

| Part | Meaning |
| --- | --- |
| `proxy` | The proxy object itself receiving the call, not the business target. |
| `method` | The `java.lang.reflect.Method` object describing the method called through the proxy: name, parameters, return type, annotations, and declaring class. |
| `args` | Argument values in declaration order, boxed when arguments are primitive types; may be `null` if the method has no parameters. |
| Return value / `throws Throwable` | The handler returns a value matching the invoked method signature or throws an error; the proxy class returns the result or exception to the caller per Java rules. |

Note that `method` is **metadata describing the method**, whereas `args` is **data for the current invocation**. Two calls to the same method can pass through the handler with different `args` values.

Forwarding is not equivalent to `method.invoke(proxy, args)` inside the handler. That call normally loops back into the proxy itself, causing `invoke` to be called repeatedly and potentially leading to `StackOverflowError`. If you want to delegate, invoke the method on a **separate compatible target** or execute the logic directly.

## 4. Complete Java 17+ example: calling a proxy, handler receives the call

Create the file `ProxyInvokeDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyInvokeDemo {
    public interface GreetingService {
        String greet(String name);
        void ping();
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            System.out.println("invoke: " + method.getName());

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            return switch (method.getName()) {
                case "greet" -> "Hello, " + arguments[0];
                case "ping" -> null;
                default -> throw new UnsupportedOperationException(
                        method.getName());
            };
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] { GreetingService.class },
                handler
        );

        System.out.println(service.greet("Lan"));
        service.ping();
        System.out.println(service.toString());
        System.out.println(service.equals(service));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ProxyInvokeDemo.java
java ProxyInvokeDemo
```

Exact stdout:

```text
invoke: greet
Hello, Lan
invoke: ping
invoke: toString
GreetingProxy
invoke: equals
true
```

Step-by-step explanation:

1. `Proxy.newProxyInstance(...)` creates an object implementing `GreetingService`. No `GreetingServiceImpl` class needs to be written.
2. `service.greet("Lan")` reaches the handler with `method.getName()` as `"greet"` and `arguments[0]` as `"Lan"`. The handler prints the method name and returns a string. The caller receives that string as the result of `greet`.
3. `service.ping()` also reaches the handler. A `void` method carries no return value to the caller; the handler returns `null`.
4. `service.toString()` and `service.equals(service)` are both routed by the JDK proxy to the handler. For the three special methods `equals`, `hashCode`, and `toString`, the `Method` passed in has `Object.class` as its declaring class. The example handles them intentionally.
5. `proxy == arguments[0]` in the `equals` branch checks reference identity, avoiding calling `proxy.equals(...)` again from the handler.

The example intentionally answers directly inside the handler to make the mechanism clear. In practice, handlers often also delegate to a target.

## 5. When the handler delegates to a target via Reflection

For proxies used to add logging, timing, or security, the handler commonly wraps the original call in the sequence: **before call → invoke target → after call**. Keep these distinct:

- `proxy`: the intermediary object the caller is using.
- `target`: the real business implementation, existing independently.
- `method.invoke(target, arguments)`: the reflective call on the target; this is an action **the handler chooses** to perform.

Standalone example `ForwardingProxyDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ForwardingProxyDemo {
    public interface Calculator {
        int divide(int left, int right);
    }

    public static final class DefaultCalculator implements Calculator {
        @Override
        public int divide(int left, int right) {
            return left / right;
        }
    }

    public static void main(String[] args) {
        Calculator target = new DefaultCalculator();

        Calculator proxy = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] { Calculator.class },
                (proxyObject, method, actualArgs) -> {
                    System.out.println("before: " + method.getName());
                    try {
                        return method.invoke(target, actualArgs);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    } finally {
                        System.out.println("after: " + method.getName());
                    }
                }
        );

        System.out.println("result: " + proxy.divide(8, 2));

        try {
            proxy.divide(1, 0);
        } catch (ArithmeticException ex) {
            System.out.println("caught: " + ex.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac ForwardingProxyDemo.java
java ForwardingProxyDemo
```

Stdout:

```text
before: divide
after: divide
result: 4
before: divide
after: divide
caught: ArithmeticException
```

In the first call, `proxy.divide(8, 2)` goes to the handler; the handler invokes `method.invoke(target, actualArgs)`, the target computes `8 / 2` and returns the integer `4`. Reflection returns an `Object` holding an `Integer`; the proxy class unboxes it to `int` for the caller.

In the second call, the target throws `ArithmeticException` due to division by zero. `Method.invoke` wraps the exception from the target method in `InvocationTargetException`. The handler extracts `ex.getCause()` and throws the real cause; `finally` still runs. Thus the caller catches `ArithmeticException`. If `InvocationTargetException` itself were thrown directly out of the handler, it is a checked exception not declared in `divide`'s signature and could be wrapped again by the proxy in `UndeclaredThrowableException`, making error handling harder.

In larger problems, control access to the target, handle exceptions properly, and ensure logging/transaction logic does not omit the failure branch.

## 6. Verifying the scope of call forwarding

The two examples above show **the same dispatch mechanism with two different handling approaches**:

- `ProxyInvokeDemo` has no target: `greet()` and `ping()` reach the handler, and the handler provides the result itself. Thus `invoke: greet` appears before the greeting string; `ping` returns `null` because the method is `void`.
- `ForwardingProxyDemo` has a target: the handler receives `divide`, prints `before`, and explicitly invokes `method.invoke(target, actualArgs)`. `finally` prints `after` even when the target throws `ArithmeticException`.

Practical point to remember: if you call `target.divide(8, 2)` directly, the proxy's handler **does not run**, even though the target implements the same interface. If the target calls another method on itself via `this`, that call does not automatically route back through the outer proxy either. Therefore, call interception depends on the **actual receiver**, not on whether methods share the same name.

## 7. What happens when the handler returns a result or throws an error?

When the handler finishes, the proxy class must satisfy the interface method's return type and exception contract:

| Situation | Observed result at caller |
| --- | --- |
| Handler returns `"Hello, Lan"` for a method returning `String` | Caller receives that exact string |
| Handler returns `Integer(4)` for a method returning `int` | Proxy unboxes to `4` |
| Handler returns `null` for a `void` method | Completes with no return value |
| Handler returns `null` for a method returning a primitive | `NullPointerException` at the type-conversion step |
| Handler throws `RuntimeException` or `Error` | Caller receives it directly under unchecked rules |
| Handler throws a checked exception outside the interface's `throws` | Proxy wraps it in `UndeclaredThrowableException` |

If the target throws `ArithmeticException` during `Method.invoke`, Reflection wraps it in `InvocationTargetException`; `ForwardingProxyDemo` intentionally throws `ex.getCause()` so the caller sees the real error. Skipping this step can cause the checked wrapper to be wrapped once more by the proxy.

## 8. Three special dispatch paths to avoid misunderstanding

**`Object` methods:** `equals(Object)`, `hashCode()`, and `toString()` are routed by the proxy to the handler; `Method.getDeclaringClass()` on these three calls is `Object.class`. `getClass()` is `final`, so it is not intercepted by this mechanism. If you print the proxy itself inside the handler, the `toString()` call can loop back into the handler and cause recursion.

**Default methods:** an interface's `default` body does not automatically run before the handler. On Java 16+, the handler can use `InvocationHandler.invokeDefault(proxy, method, args)` for a valid default method if it decides to execute the body. `method.invoke(proxy, args)` calls the proxy itself and risks recursion.

**Multiple interfaces:** when two interfaces have the same method name and parameter list, the `Method` passed to the handler can depend on interface order at proxy creation time, and covariant return types have their own rules. The handler does not receive information about which interface the caller cast the proxy to. Design dispatch around an explicit contract, not solely by method name.

## 9. Self-check

1. In `ProxyInvokeDemo`, would removing the target object cause `greet` to fail? **No**, the handler returns the result itself.
2. In `ForwardingProxyDemo`, why is `after: divide` still printed when dividing by zero? Because the handler uses `finally` around the target call.
3. If you replace the receiver in `method.invoke(target, actualArgs)` with the proxy from the same call, what happens? Dispatch loops back to the handler, easily causing infinite recursion.
4. If a method returning `int` is called and the handler returns `null`, does the error happen before the handler returns? Not necessarily; the proxy class must unbox the result and will throw `NullPointerException`.
5. Does `service.toString()` reach the handler? **Yes**. Does `service.getClass()` reach the handler? **No**, because `getClass` is a `final` method on `Object`.

**Takeaway:** calls on a **proxy instance** trigger the handler. The handler can handle them itself, call a target, or run a selected default method; the caller only sees results/exceptions conforming to the interface signature. Tracing the receiver of each call is the surest way to predict behavior.

### Official Documentation

- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
