# Proxy and InvocationHandler in Java

## 1. From an interface call to a shared handler

Suppose multiple operations need to log before and after running. If logging code is written into every business method, code is duplicated and business logic gets mixed with call tracing.

**JDK dynamic proxy** creates an object implementing the chosen interfaces at runtime. When calling code uses that object through an interface, the call is routed to a shared handler: `InvocationHandler`.

The handler can:

- Add behavior before or after the call.
- Delegate to a real object.
- Compute a result itself without a real object.
- Reject an operation or translate errors according to the interface contract.

Roles to keep separate:

| Role | Responsibility |
| --- | --- |
| Interface | Contract seen by the calling code |
| Proxy instance | Object receiving calls through the interface |
| InvocationHandler | Decides how to handle the described call |
| Target object, if any | Executes the business logic delegated by the handler |

A proxy does not automatically imply a hidden target object inside. A target object is one choice of how to write the handler.

## 2. Call dispatch mechanism

A typical delegation flow:

~~~text
Calling code
  -> method on proxy via interface
  -> InvocationHandler.invoke(proxy, method, args)
  -> additional processing
  -> method.invoke(target, args), if delegating
  -> result or exception returns to calling code
~~~

Two main APIs:

~~~java
Proxy.newProxyInstance(loader, interfaces, handler)
~~~

This is an illustrative expression, with variables already prepared. The method returns `Object`; calling code casts it to the interface the proxy was created to implement.

The handler implements the method:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

The line above represents the signature of `InvocationHandler.invoke`, not a complete method with a body.

Meaning of the parameters:

- `proxy`: the proxy object itself receiving the call, **not the target object**.
- `method`: metadata of the invoked interface method; the declaring class may be a parent interface from which the provided interface inherits the method.
- `args`: the arguments, with primitive values boxed; `null` if the method takes no arguments.

Obtaining a `Method` describing the call does not mean the handler must use Reflection to invoke a real object. The handler can choose another handling strategy.

## 3. Complete example: adding tracing and delegation

Save as `ProxyHandlerDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;

public class ProxyHandlerDemo {
    public interface GreetingService {
        String greet(String name);
        int calls();
    }

    public static final class RealGreetingService
            implements GreetingService {
        private int count;

        @Override
        public String greet(String name) {
            String cleaned = Objects.requireNonNull(name, "name").strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("name is blank");
            }
            count++;
            return "Hello, " + cleaned;
        }

        @Override
        public int calls() {
            return count;
        }
    }

    public static final class TracingHandler implements InvocationHandler {
        private final GreetingService target;

        public TracingHandler(GreetingService target) {
            this.target = Objects.requireNonNull(target, "target");
        }

        @Override
        public Object invoke(
                Object proxy,
                Method method,
                Object[] arguments) throws Throwable {

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            System.out.println("enter " + method.getName());
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            } finally {
                System.out.println("leave " + method.getName());
            }
        }
    }

    public static void main(String[] args) {
        GreetingService target = new RealGreetingService();
        TracingHandler handler = new TracingHandler(target);

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] {GreetingService.class},
                handler);

        System.out.println("isProxyClass="
                + Proxy.isProxyClass(service.getClass()));
        System.out.println("handlerMatches="
                + (Proxy.getInvocationHandler(service) == handler));

        System.out.println(service.greet("Lan"));
        System.out.println("calls=" + service.calls());
        System.out.println("toString=" + service);
        System.out.println("equalsSelf=" + service.equals(service));
        System.out.println("equalsTarget=" + service.equals(target));

        try {
            service.greet(" ");
        } catch (IllegalArgumentException exception) {
            System.out.println("error="
                    + exception.getClass().getSimpleName()
                    + ":" + exception.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 ProxyHandlerDemo.java
java ProxyHandlerDemo
~~~

Output:

~~~text
isProxyClass=true
handlerMatches=true
enter greet
leave greet
Hello, Lan
enter calls
leave calls
calls=1
toString=GreetingProxy
equalsSelf=true
equalsTarget=false
enter greet
leave greet
error=IllegalArgumentException:name is blank
~~~

The program runs sequentially. `RealGreetingService` tracks the count of valid greetings; the example does not build a concurrent counter.

Step-by-step walkthrough:

1. `newProxyInstance` creates an object implementing `GreetingService`.
2. `service.greet("Lan")` translates into a call to `handler.invoke`.
3. The handler prints `enter`, invokes the method on `target`, and always prints `leave` in `finally`.
4. `calls()` has no parameters, so the handler's arguments array is null. `Method.invoke` accepts null to represent no arguments.
5. The `int` result of `calls()` is boxed by Reflection when returning to the handler, and then the proxy returns a result matching the interface's `int` return type.
6. When the target object rejects a blank name, the handler unwraps the root cause from `InvocationTargetException`, so the caller receives `IllegalArgumentException`.

A proxy is identified with `Proxy.isProxyClass`, not by looking for a JDK-generated class name string. `Proxy.getInvocationHandler` retrieves the handler attached to that exact proxy instance.

## 4. Separating the proxy, handler, and target roles

The example above has two **distinct** objects: `service` is the proxy receiving calls from the caller, while `target` is the `RealGreetingService` performing the business logic. The handler connects the two objects via `method.invoke(target, arguments)` and only logs around that delegated call. A direct `target.greet("Lan")` call **does not go through the handler**; only calls that the caller sends to `service` are intercepted.

There is no rule requiring a handler to own a target. A mock or RPC stub can answer on its own based on `method` and `args`. When there is no target, the handler must still produce a result of the right type or throw an exception consistent with the interface contract.

**Do not delegate back to the proxy:** `method.invoke(proxy, arguments)` executes the same method again on the proxy object, which triggers the handler again and can loop until `StackOverflowError`. When logging, avoid concatenating strings with `proxy` itself unless a clear `toString()` policy is in place.

## 5. Four boundaries a handler must uphold

| Boundary | What to know when writing a handler |
| --- | --- |
| Arguments | `args == null` if the method takes no parameters; primitives are boxed. |
| Return value | An `int` requires a corresponding `Integer`; `null` for a primitive type causes `NullPointerException`; a wrong object type can cause `ClassCastException`. |
| Exceptions | `Method.invoke(target, args)` wraps errors from the target in `InvocationTargetException`; to forward the real error, typically extract `getCause()`. A checked exception leaving the handler must match the interface's `throws` clause, otherwise the proxy may wrap it in `UndeclaredThrowableException`. |
| `Object` methods | `equals`, `hashCode`, and `toString` also reach the handler; the example uses proxy identity for equality/hash and the string `GreetingProxy`. |

For interface default methods, the call still goes through the handler. If you genuinely want to run the default body, since Java 16 there is `InvocationHandler.invokeDefault`; do not use `Method.invoke(proxy, args)` as a substitute. Separate articles on return values, checked exceptions, default methods, and `Object` methods will go deeper into specific conditions.

## 6. When to use this pattern?

Choose JDK dynamic proxy if callers work through an **interface** and you want to alter how calls are handled at runtime: validation, logging, metrics, mocking, or remote service calls. `newProxyInstance` creates a proxy class implementing those interfaces; it does not make the proxy a subclass of `RealGreetingService`.

The class loader must see each requested interface properly. Additional considerations include Java module boundaries, `sealed`/`hidden` interfaces, methods with identical signatures, and access rules for `non-public` interfaces when used in plugin/module environments. Using a single public interface on the regular classpath, as in the example, helps focus on the call flow before moving to harder cases.

## 7. Self-check from the example

1. Does `Proxy.newProxyInstance` instantiate `RealGreetingService` automatically? **No**; the target is created independently and the handler receives the target provided by application code.
2. Why does `service.greet("Lan")` print `enter/leave`, while `target.greet("Lan")` does not? **The objects receiving the call are different**; only the proxy routes calls through the handler.
3. `calls()` takes no parameters; does the handler receive a single-element array? **No**; `arguments` is `null`.
4. Why is it necessary to unwrap `InvocationTargetException` when forwarding the original error? To preserve the business cause and avoid exposing an undeclared checked wrapper outside the interface's `throws` clause to the caller.
5. Is using `Method.invoke(target, arguments)` mandatory? **No**; the handler can execute another strategy itself and return a value matching the contract.

**Takeaway:** JDK proxy provides an object callable through an interface, while `InvocationHandler` defines the call behavior. The target, if any, is a choice of the handler. Always separate the **proxy receiving calls**, the **handler coordinating execution**, and the **target executing business logic** to avoid accidentally calling back into the proxy.

### Official Documentation

- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
