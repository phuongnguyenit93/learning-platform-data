# Invoking Default Methods with `InvocationHandler.invokeDefault` in Java

## 1. The problem: default methods also pass through InvocationHandler

A JDK dynamic proxy is an object created with `java.lang.reflect.Proxy` to implement one or more interfaces. When calling a method on the proxy, the call is routed to `InvocationHandler.invoke(proxy, method, args)`, even when the interface provides a `default method` body. Therefore, if the handler wants to **execute the default body** instead of computing a result itself, it must explicitly forward the call.

Since **Java 16**, the `InvocationHandler.invokeDefault` API provides a direct way to do this. For Java 17+, this is the clear choice when writing dynamic proxies that support default methods.

```java
// Pattern used inside InvocationHandler.invoke:
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

This is an **illustrative snippet placed inside a handler**, not a standalone program. `method.isDefault()` helps distinguish a true default method from abstract interface methods, `Object` methods, and other methods.

## 2. Syntax, parameters, and mechanism

API signature:

```java
public static Object invokeDefault(
        Object proxy, Method method, Object... args) throws Throwable;
```

| Parameter | Meaning |
| --- | --- |
| `proxy` | The **dynamic proxy** object handling the call. |
| `method` | `Method` representing a **valid default method** declared on a proxy interface or inherited by that interface. |
| `args` | Arguments passed to the default method, matching parameter count and types; may be `null` when the method has no parameters. |
| Return value | `Object` containing the result returned by the default method body (or `null` if the method returns `void`). |

`InvocationHandler.invokeDefault(proxy, method, args)` executes the default body with semantics close to the JVM `invokespecial` instruction, equivalent to the idea of calling `InterfaceName.super.method(...)` from the proxy class. This is **not** a normal call through `Method.invoke(proxy, ...)`.

Important condition: `method` must be a default method resolvable through the interfaces of **that exact proxy**. You cannot grab an arbitrary default method from an unrelated interface and ask the proxy to execute it. If a proxy interface overrides a parent interface's default method, trying to directly invoke the parent version using an older `Method` may no longer be valid.

Flow diagram:

```text
client calls proxy.defaultMethod(...)
    → JVM routes into handler.invoke(proxy, method, args)
        → method.isDefault() == true
            → InvocationHandler.invokeDefault(proxy, method, args)
                → runs default method body in interface
                    → returns result to handler then to client
```

If inside the default method body it calls another interface method via `this`, that virtual call can still pass through the proxy's handler. The handler must be able to handle that follow-up call as well.

## 3. Standalone Java 17+ example

Save the file `InvokeDefaultDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class InvokeDefaultDemo {
    public interface TextService {
        String code();

        default String greeting(String name) {
            return "Hello, " + name + " from " + code();
        }

        default String plain() {
            return "DEFAULT";
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, callArgs) -> {
            if (method.isDefault()) {
                System.out.println("handler default: " + method.getName());
                return InvocationHandler.invokeDefault(
                        proxy, method, callArgs);
            }

            if (method.getName().equals("code")
                    && method.getParameterCount() == 0) {
                return "proxy";
            }

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "TextServiceProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == callArgs[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            throw new UnsupportedOperationException(method.toString());
        };

        TextService service = (TextService) Proxy.newProxyInstance(
                TextService.class.getClassLoader(),
                new Class<?>[] { TextService.class },
                handler);

        System.out.println(service.greeting("An"));
        System.out.println(service.plain());
        System.out.println(service.code());
        System.out.println(service.toString());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 InvokeDefaultDemo.java
java InvokeDefaultDemo
```

Exact stdout:

```text
handler default: greeting
Hello, An from proxy
handler default: plain
DEFAULT
proxy
TextServiceProxy
```

Step-by-step walkthrough:

1. `service.greeting("An")` reaches the handler. Because `greeting` is a default method, `method.isDefault()` is `true` and `invokeDefault` runs the body written in `TextService`.
2. Inside the body of `greeting` is `code()`; this is an abstract method invoked on the proxy, so the handler receives the `code` call and returns `"proxy"`. The combined result becomes `Hello, An from proxy`.
3. `plain()` takes no parameters: `callArgs` in the handler may be `null`, and passing that value directly to `invokeDefault` is valid.
4. `code()` is not a default method: the handler supplies the result itself.
5. `toString()` belongs to the group of `Object` methods routed by the proxy to the handler; a dedicated branch prevents non-default calls from all throwing errors. The example also handles `equals` and `hashCode` by proxy identity.

## 4. Why not use Method.invoke(proxy, args)?

Suppose inside the handler you wrote:

```java
// Wrong when the goal is to run the default method body:
return method.invoke(proxy, args);
```

`Method.invoke` calls the method on the `proxy` object itself. That object routes the call back to the handler, leading to an infinite loop and risking `StackOverflowError`. `InvocationHandler.invokeDefault` enters **the specified default body**, solving the problem properly.

Nor can you write `SomeInterface.super.method(...)` directly inside a handler lambda: that syntax is only valid in a Java context permitting a superinterface default method call, not a dynamic call based on a `Method` object.

Prior to Java 16, workarounds typically involved `MethodHandles.Lookup` and module access permissions; do not copy old examples into Java 17+ when the `invokeDefault` API already meets the need.

## 5. Inheritance, overriding, and multiple default methods with matching signatures

**Inheritance:** if `Child extends Parent` and `Child` does not override the default method `Parent.run()`, a proxy implementing only `Child` can still invoke the default body inherited from `Parent` via `invokeDefault`. The `Method` received by the handler may have `getDeclaringClass() == Parent.class`.

**Overriding:** if `Child` later redefines `default run()`, the effective method is `Child`'s version. A handler that cached `Parent.class.getMethod("run")` and forces `invokeDefault` to call the parent version may receive `IllegalArgumentException`, because the parent version is no longer a valid resolution target through `Child`. This is something to check when upgrading interface libraries.

**Two independent interfaces with the same default method:** the handler can explicitly choose one version by obtaining the exact `Method` from the desired interface. The following standalone example produces `second` in both cases, regardless of whether the client casts the proxy to `First` or `Second`:

Save the file `ChooseDefaultDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ChooseDefaultDemo {
    public interface First {
        default String origin() { return "first"; }
    }

    public interface Second {
        default String origin() { return "second"; }
    }

    public static void main(String[] args) throws Exception {
        Method chosen = Second.class.getMethod("origin");

        InvocationHandler handler = (proxy, method, callArgs) -> {
            if (method.getName().equals("origin")) {
                return InvocationHandler.invokeDefault(
                        proxy, chosen, callArgs);
            }
            throw new UnsupportedOperationException(method.toString());
        };

        Object proxy = Proxy.newProxyInstance(
                ChooseDefaultDemo.class.getClassLoader(),
                new Class<?>[] { First.class, Second.class },
                handler);

        System.out.println(((First) proxy).origin());
        System.out.println(((Second) proxy).origin());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ChooseDefaultDemo.java
java ChooseDefaultDemo
```

```text
second
second
```

The example above explicitly chooses `Second.origin()`. It does **not** mean Java automatically prefers `Second`; interface order and the initial `Method` passed to the handler should not be relied upon in place of a business decision. If you want to choose based on the caller's static type, design distinct interfaces or entry points: for two matching signatures, the handler does not automatically receive information about which interface the client cast to.

## 6. Input validation, errors, and exceptions

| Case | Behavior / handling |
| --- | --- |
| `method.isDefault() == false` | Do not pass abstract or `Object` methods to `invokeDefault`; handle/delegate them separately. |
| `proxy` is not a dynamic proxy, or `method` is not a valid default method of the proxy | `IllegalArgumentException`. |
| `method` was overridden by a proxy interface, invalidating the old target | May throw `IllegalArgumentException`; update the selected `Method` to the effective interface. |
| Wrong argument count or incompatible argument types, including primitive unboxing | `IllegalArgumentException`. |
| `proxy == null` or `method == null` | `NullPointerException`. |
| Class declaring the default method is inaccessible from the call site | May throw `IllegalAccessException`. |
| The default method body itself throws an exception | `invokeDefault` can throw that `Throwable`; the interface method's `throws` contract must be considered. |

The handler has the signature `Object invoke(...) throws Throwable`, so it can propagate a `Throwable` from `invokeDefault` without wrapping it into a `RuntimeException`. If a checked exception not declared by the interface method escapes the handler, the call on the proxy may wrap it in `UndeclaredThrowableException`. For primitive-returning methods, the result returned by the handler must match the corresponding wrapper; returning `null` will fail when the proxy needs to unbox.

To use safely, check `method.isDefault()` first, pass the actual proxy, forward `args` intact (including `null` when there are no parameters), and handle remaining methods separately.

## 7. Common pitfalls and how to avoid them

- **Calling back into the proxy via reflection:** `method.invoke(proxy, args)` is not the way to run a default body; use `invokeDefault`.
- **Assuming default methods run automatically:** dynamic proxies route calls to the handler; if you want to run the default body you must explicitly choose to do so.
- **Confusing `isDefault()` with `!isAbstract()`:** `Object` methods are also non-abstract, yet they are not default methods.
- **Looking up a `Method` by name without considering proxy interfaces:** only use a valid, effective, and accessible default method.
- **Assuming `args` is always non-`null`:** the handler receives `null` when a method has no parameters; if reading `args[0]`, be sure the method requires arguments.
- **Overlooking follow-up calls from inside the default method:** a default body can invoke another interface method and trigger the handler a second time.
- **Not checking JDK compatibility:** `InvocationHandler.invokeDefault` only exists starting in Java 16; compiling with `--release 11` cannot call this API.
- **Forgetting inheritance and overriding:** adding a new default method in a sub-interface can change which method `invokeDefault` is permitted to invoke.

## 8. Self-check questions

1. **Why is `method.invoke(proxy, args)` unsuitable for running a default method from a handler?** Because it invokes the method on the proxy again, sending the call back into the handler itself and causing infinite recursion.
2. **What happens when a default method calls an abstract method on the same interface?** The call executes on the proxy; the handler receives the abstract method and must handle it.
3. **A proxy implements `First` and `Second`, both having `default origin()`. Can you select `Second`?** Yes: obtain `Second.class.getMethod("origin")` and pass that method to `InvocationHandler.invokeDefault`, provided it is valid for the proxy's interfaces.
4. **Can `null` be passed for `args`?** Yes, when the default method has 0 parameters; for methods with parameters, you must pass the valid count and types of arguments.
5. **Can this API be used on Java 11?** No; the API was introduced in Java 16.

**Takeaway:** `InvocationHandler.invokeDefault` is the bridge from `InvocationHandler` to **the valid interface default method body on a dynamic proxy**. Use `Method.isDefault()` to identify them, handle abstract/`Object` methods separately, and carefully check inheritance, overriding, accessibility, and arguments.

Reference: [Java 17 Javadoc — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html).