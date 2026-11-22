# 10.4 Reading `Method`, proxy receiver, and `args`; handling zero-argument calls

## 1. Objectives and Context

The JDK's **dynamic proxy** (`java.lang.reflect.Proxy`) allows creating an object that implements one or more **interfaces** at runtime. Each method call is dispatched to `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`, enabling frameworks to perform logging, tracing, authorization, caching, or delegation to a real object.

A small but very important detail: when a method **has no parameters**, `args` in `InvocationHandler` is normally **`null`**, **not** an empty array `new Object[0]`. Reading `args.length`, iterating over `args`, or forwarding `args` without understanding this contract can cause a `NullPointerException` or incorrect recording.

This lesson focuses on the three inputs of the handler:

- **`proxy`:** the receiver is **the proxy object itself** on which the caller invoked the method, not the real business object.
- **`method`:** metadata of type `java.lang.reflect.Method` describing **the method invoked via the interface or one of the methods of `Object`**.
- **`args`:** `Object[]` containing the **actual arguments** provided to the method, or `null` if the method has no parameters.

You will learn how to properly check zero-argument cases, `null` arguments, varargs, handle `equals/hashCode/toString`, avoid infinite recursion, forward calls using Reflection, and preserve business exceptions. The examples use Java 17+.

> **Core rule:** Treat `proxy`, `Method`, and `args` as three distinct pieces of information. `proxy` indicates *the object receiving the call*, `Method` indicates *the invoked method signature*, and `args` indicates *the argument values* — with the special exception `args == null` when the parameter count is 0.

## 2. How a Call Goes Through a Dynamic Proxy

Suppose there is an interface:

```java
interface Greeting {
    String hello();
    String greet(String name);
}
```

A proxy object implementing `Greeting` can be created as follows:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

The above is a **snippet**, assuming a variable `handler` of type `InvocationHandler` and an import of `java.lang.reflect.Proxy` already exist. With the call:

```java
String result = proxy.greet("An");
```

Conceptual processing flow:

```text
Caller
  |
  | proxy.greet("An")
  v
JDK-generated proxy class
  |
  | handler.invoke(proxy, Method[greet(String)], Object[]{"An"})
  v
InvocationHandler
  |
  | inspect Method + args; choose handling
  | may call delegate.greet("An")
  v
Return value from handler
  |
  v
Proxy returns result to caller
```

Important details:

1. Caller source code still calls `proxy.greet(...)` using normal interface syntax. The caller does not directly call `handler.invoke(...)`.
2. The JDK-generated proxy class holds an `InvocationHandler`, constructs the appropriate `Method` metadata, and invokes the handler for most interface methods and the specified `Object` methods.
3. `InvocationHandler.invoke` **does not automatically call the real implementation**. The handler must decide on its own to return a value, forward to a delegate, or throw an exception.
4. When a delegate is present, `proxy` and `delegate` are **two different objects**. Mistakenly calling `method.invoke(proxy, args)` inside the handler will loop back to the handler and may cause infinite recursion.
5. JDK proxies implement **interfaces**; they do not turn an arbitrary business class into a proxy subclass like some other bytecode libraries do.

### 2.1. The `InvocationHandler.invoke` Contract

Signature according to the JDK:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

Meaning of parts:

| Parameter | Runtime type | Meaning | Pitfall |
| --- | --- | --- | --- |
| `proxy` | `Object` | The actual proxy object receiving the call | Not the delegate; do not unconditionally call `proxy.toString()` for logging inside the handler |
| `method` | `Method` | Method metadata dispatched to the handler | `getDeclaringClass()` may be an interface or `Object`, not necessarily the proxy class or delegate class |
| `args` | `Object[]` or `null` | The arguments of the invoked method | `null` when the method has no arguments; a `null` element when the caller passes a null value is a different case |
| Return | `Object` | Result returned by the handler for the proxy to pass back to the caller | Primitive returns require a valid wrapper; void returns are ignored |
| `throws Throwable` | Exception | The handler can report errors | Checked exceptions not declared by the interface may be wrapped by the proxy into `UndeclaredThrowableException` |

`Method` is a **metadata object**, not a business object. When a proxy implements the `Greeting` interface, `method.getDeclaringClass()` for `greet` is usually the `Greeting.class` interface. `method.getDeclaringClass()==proxy.getClass()` is not the right condition to identify a call.

## 3. Reading `Method`: Name, Signature, Owner, and Flags

Very useful `Method` APIs inside a handler:

| API | What is it used for? | Example / note |
| --- | --- | --- |
| `getName()` | Java name of the method | `"greet"`, `"toString"`, `"equals"` |
| `getDeclaringClass()` | Declaring type of the method currently dispatched to the handler | Interface or `Object.class`; with multiple interfaces, also depends on order and signature |
| `getParameterCount()` | Number of **declared** parameters of the method | `hello()` → 0; `greet(String)` → 1; `join(String...)` → **1** |
| `getParameterTypes()` | `Class<?>[]` array of parameter types after erasure | `join(String...)` has `String[].class` |
| `getGenericParameterTypes()` | Generic types if metadata has the information | May return `TypeVariable`/`ParameterizedType` |
| `getReturnType()` | Return type `Class<?>` | `void.class`, `int.class`, `String.class` |
| `isVarArgs()` | Did the method declare Java varargs? | `join(String...)` → true; does not mean `args` has arbitrary length |
| `isDefault()` | Is it a default method of an interface? | Can be handled with `InvocationHandler.invokeDefault` on Java 17+ |
| `getModifiers()` | Modifier flags of the method | Useful when recording metadata, does not replace checking the method signature |

Example of a handler that can log **without calling the business method**:

```java
// Snippet inside InvocationHandler.invoke(...).
System.out.println("method=" + method.getName());
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("params=" + method.getParameterCount());
System.out.println("return=" + method.getReturnType().getSimpleName());
System.out.println("varargs=" + method.isVarArgs());
```

**You should not dispatch business logic solely by `method.getName()`** if the interface has overloads. `find(String)` and `find(long)` have the same name but different parameters. Use `getParameterTypes()` as well or match the full `Method` when precision is needed.

### 3.1. The Owner Is the Interface, Not the Implementation

Given:

```java
interface Service { String ping(); }
final class ServiceImpl implements Service {
    public String ping() { return "pong"; }
}
```

When calling `proxy.ping()`, the `method` parameter may be `Service.class.getMethod("ping")`. It is declared on the interface, even if the handler later chooses to forward to `ServiceImpl`. Some frameworks need annotation metadata on the **interface**, while some need annotations on the **implementation**; there must be an explicit lookup policy rather than assuming they are the same.

With inherited interfaces, the declaring class can be a parent interface. With multiple interfaces declaring the same signature, see section 10 on `Method` selection. Therefore, do not use `method.getDeclaringClass()` as the sole identifier of the "source method" without considering the set of interfaces implemented by the proxy.

### 3.2. Primitives and `void`

Suppose an interface has:

```java
int size();
void touch();
```

If the handler calls the delegate using `Method.invoke`, the `int` result will be boxed into an `Integer` in the returned `Object`. The proxy will unbox it when returning from `size()` to the caller. If the handler returns `null` from a method declared with a primitive type, a `NullPointerException` may occur when the proxy tries to unbox it. If the wrong wrapper type is returned, a `ClassCastException` may occur.

For `void touch()`, the handler can return `null`; in the proxy model, the handler's return value for a void method is not used by the caller. **Do not** treat the handler returning `null` as proof that the business call failed: the void method may have run successfully.

## 4. `proxy` Is the Proxy Receiver, Not the Delegate

Suppose:

```java
TaskService service = (TaskService) Proxy.newProxyInstance(
        TaskService.class.getClassLoader(),
        new Class<?>[]{TaskService.class},
        new LoggingHandler(realService));
```

In `LoggingHandler.invoke(proxy, method, args)`:

- `proxy == service` in object identity (if `service` is the receiver that was called).
- `Proxy.isProxyClass(proxy.getClass())` is normally true for a JDK proxy class.
- `method.getDeclaringClass()` is usually `TaskService.class` for business methods, or `Object.class` for `toString`/`equals`/`hashCode` methods.
- `realService` is the **delegate** stored by the handler, not the `proxy` parameter.

A dangerous mistake:

```java
// WRONG: if Method can be invoked on proxy, this usually loops back to the handler.
return method.invoke(proxy, args);
```

For example, `method` represents `TaskService.ping()`. Calling `method.invoke(proxy,args)` will trigger `proxy.ping()` again; the proxy calls `handler.invoke(...)` again; the handler calls `method.invoke(proxy,args)` again... and this can lead to a `StackOverflowError`. **Do not treat the proxy receiver as the delegate.**

The correct way to forward when a matching implementation exists:

```java
Object[] forwarded = args == null ? new Object[0] : args;
return method.invoke(realService, forwarded);
```

This is a **snippet**; `realService` must implement the interface or be compatible with the invoked `Method`. For zero-argument methods, passing an empty array to `Method.invoke` is clear and consistent. Do not use `method.invoke(proxy,...)`.

### 4.1. Logging the Receiver Without Accidentally Re-entering the Handler

This way of logging can re-enter the handler:

```java
// RISK: string concatenation calls proxy.toString()!
System.out.println("proxy=" + proxy);

// SIMILAR RISK: a formatter may call equals/hashCode/toString
// of the proxy itself if it puts it into a data structure that needs comparison.
```

Because `toString()` on a dynamic proxy also goes through `InvocationHandler`, logging `proxy` from inside `invoke` can trigger **a nested call**. If you keep logging that way, it can loop forever.

To inspect object identity without calling `proxy.toString()`, you can log:

```java
// Snippet inside the handler.
System.out.println("proxyClass=" + proxy.getClass().getName());
System.out.println("identity=" + System.identityHashCode(proxy));
```

`System.identityHashCode` uses the identity hash code and **does not call `proxy.hashCode()`**. However, the JDK-generated proxy class name should not be hard-coded as a stable identifier across runs; the practice example below only prints the boolean `Proxy.isProxyClass(...)`, avoiding reliance on the generated class name.

When `args` contains the proxy itself (such as `proxy.equals(proxy)`), simply calling `Arrays.deepToString(args)` can also invoke `toString` on the proxy and re-enter. The formatter in the main example will recognize `value == proxy` and print `<self>` instead of calling `toString`.

## 5. `args == null` When a Method Has No Arguments

This is the most important point of the topic.

By the `InvocationHandler.invoke` contract, **`args` is `null` if the method has no parameters**. The following calls normally enter the handler with `args == null`:

```java
service.ping();
service.size();
service.touch();
service.toString();
service.hashCode();
```

Those methods have `method.getParameterCount() == 0`. During handling, do not use:

```java
// WRONG: NullPointerException if args == null.
int length = args.length;

// WRONG: enhanced for cannot iterate over null.
for (Object value : args) {
    System.out.println(value);
}

// WRONG: inappropriate for a method with no parameters.
Object first = args[0];
```

### 5.1. Safe Null-Guard Rules

If you only need to count the actual number of arguments:

```java
int argc = args == null ? 0 : args.length;
```

If you need to iterate or forward:

```java
Object[] effectiveArgs = args == null ? new Object[0] : args;
for (Object value : effectiveArgs) {
    // Process each argument.
}
```

If you need to log elements, preserve the distinction between **the handler receiving null** and **the handler receiving an empty array** when debugging:

```java
String label = args == null ? "<null>" : Arrays.deepToString(args);
```

`Arrays.deepToString(args)` in this example is a **snippet** and is only suitable when values do not cause side effects when converted to strings; if `args` contains a proxy or an object with a dangerous `toString`, a more careful formatter is needed.

Do not turn "`args == null`" into an assertion that **the caller passed a null parameter**. Both `method.getParameterCount()` and the contents of `args` must be used to distinguish them.

### 5.2. Three Different Cases: 0 Parameters, 1 Null Parameter, and Empty Array

| Call | `method.getParameterCount()` | `args` at handler | Explanation |
| --- | --- | --- | --- |
| `service.ping()` | 0 | `null` | Method declares no parameters |
| `service.echo(null)` | 1 | `new Object[]{null}` structurally | Method has one parameter, and its value is null |
| `service.join()` with `join(String...)` | 1 | `new Object[]{new String[0]}` structurally | Varargs is still **one array parameter** in the compiled signature |
| `service.join((String[]) null)` | 1 | `new Object[]{null}` structurally | The array parameter was passed **null** by the caller |
| `service.equals(null)` | 1 | `new Object[]{null}` structurally | `equals(Object)` has one parameter, not a zero-argument method |

The `new Object[]{...}` forms in the table are **structural illustrations**, not a guarantee that the JDK creates the exact object by calling an array constructor as in the syntax. What matters is **the array length and contents**.

If you want to detect "no arguments" independently of array representation in the handler, use `method.getParameterCount() == 0`; if you want to avoid NPE when processing actual data, use an `args == null` guard.

### 5.3. Do Not Check `args.length == 0` Before Checking `args == null`

The following conditional **can still throw an NPE**:

```java
// WRONG because the first operand already accesses args.length.
if (args.length == 0 || args == null) {
    // ...
}
```

Write it with proper short-circuiting:

```java
if (args == null || args.length == 0) {
    // Safe when accessing the array.
}
```

However, with JDK dynamic proxies, **a null array and an empty array are not two cases that the caller controls with the same method**. When you only want to determine whether a method declares no parameters, `method.getParameterCount() == 0` is the better semantic criterion.

## 6. Properly Forwarding Calls to a Delegate

A logging proxy typically has the responsibilities to:

1. Receive `Method` and arguments from the proxy.
2. Decide whether to handle special methods (`equals/hashCode/toString`) or not.
3. Normalize `args` for safe usage.
4. Invoke the method on the **real implementation object** if appropriate.
5. Return the exact result without losing business exceptions.

Common structure:

```java
@Override
public Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable {

    // Object methods may need their own policy.
    if (method.getDeclaringClass() == Object.class) {
        return handleObjectMethod(proxy, method, args);
    }

    Object[] safe = args == null ? new Object[0] : args;
    try {
        return method.invoke(delegate, safe);
    } catch (InvocationTargetException ex) {
        throw ex.getCause();
    }
}
```

This is a **snippet**, not a standalone runnable program: `delegate` and `handleObjectMethod` must be defined. It illustrates two important points:

- `method.invoke(delegate, safe)` **actually forwards** to the appropriate object; it does not create a loop through the proxy.
- When the delegate's method throws an exception, Reflection wraps the target exception in `InvocationTargetException`. Unwrapping it with `ex.getCause()` preserves the original business exception.

### 6.1. `Method.invoke` Also Uses Java Varargs: Understand the Type of `safe`

`Method.invoke` has the signature:

```java
Object invoke(Object obj, Object... args)
```

Here `safe` is an `Object[]`. When writing `method.invoke(delegate, safe)`, Java uses that entire array as the argument list for Reflection, **not** treating it as "a single Object argument" regardless of what the target method declares.

With `join(String...)`, the handler's `safe` array contains **one element**, and that element is `String[]`. Therefore `method.invoke(delegate,safe)` passes **one array parameter** exactly as declared by the method. If you accidentally replace `safe` with an inner `String[]`, or flatten the elements according to the varargs count, the method invocation may have the wrong signature.

Another valid style that should be used intentionally for zero-arg calls:

```java
method.invoke(delegate, new Object[0]);
```

Do not use `method.invoke(delegate, (Object) safe)` when you want to pass the argument list; such a cast can make `safe` become **one** argument instead of the whole list.

### 6.2. Why Must `InvocationTargetException` Be Unwrapped?

Suppose the delegate has a method:

```java
public String fail() {
    throw new IllegalStateException("delegate failed");
}
```

When called via `Method.invoke(delegate, ...)`, Reflection throws an `InvocationTargetException` containing `IllegalStateException` inside. If the handler keeps the wrapper and throws it as is, the proxy may report a different exception than expected, or even `UndeclaredThrowableException` if a checked exception is not permitted by the interface signature.

In a handler declared with `throws Throwable`, forwarding is usually done with:

```java
try {
    return method.invoke(delegate, safeArgs);
} catch (InvocationTargetException ex) {
    throw ex.getCause(); // Preserve the exception thrown by the target method.
}
```

Do not arbitrarily re-wrap it into a `RuntimeException` if the business contract needs to distinguish checked exceptions or exception identity. Apply a separate logging policy if needed, while still preserving the original exception when appropriate.

### 6.3. Checked Exceptions and `UndeclaredThrowableException`

A proxy interface method may declare:

```java
String load() throws java.io.IOException;
```

If the handler throws `IOException` during a call to `load`, that exception is allowed by the interface. But if the handler throws a **checked exception** not allowed by the method's signature, the JDK proxy may wrap it in `java.lang.reflect.UndeclaredThrowableException`. This is a property of the proxy contract, not a bug in `args`.

A good handler needs to distinguish:

- **Business** exceptions thrown by the delegate, obtained from `InvocationTargetException.getCause()`.
- **Lookup/reflection** exceptions such as `IllegalAccessException` or `IllegalArgumentException` when the method/receiver is incompatible.
- **Proxy wrapper** exceptions when a checked exception falls outside the declaration.
- Errors from the handler's own null handling, re-entrant logging, or invalid casting.

## 7. Handling `toString`, `hashCode`, and `equals`

Three public, non-final methods of `java.lang.Object` **are routed by the JDK proxy to `InvocationHandler`** according to the proxy mechanism. They can be called indirectly by loggers, `Set`, `Map`, debuggers, or monitoring tools, even when business code does not call them explicitly.

| Method | Typical `getDeclaringClass()` | Declared parameter count | `args` in handler |
| --- | --- | --- | --- |
| `toString()` | `Object.class` | 0 | `null` |
| `hashCode()` | `Object.class` | 0 | `null` |
| `equals(Object other)` | `Object.class` | 1 | One element; may be null or the proxy itself |

Therefore, you cannot write `if (args==null) return null;` for every zero-argument method. `toString` must return a `String`; `hashCode` must return the corresponding wrapper for `int`; other business methods may need to call the delegate to obtain data.

### 7.1. Identity-Based Convention for Proxies

A simple and self-consistent policy:

```java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "TaskServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.toString());
    };
}
```

Explanation:

- `toString` returns a descriptive string **without calling `proxy.toString()` again**.
- `hashCode` uses `System.identityHashCode(proxy)`, avoiding calling `proxy.hashCode()` on itself.
- `equals` uses `proxy == args[0]`, avoiding calling `proxy.equals(other)` on itself. A `null` argument yields `false`.
- Preserves **consistency between `equals` and `hashCode`** at the identity level. Do not mix delegate-based `equals` with proxy-based `hashCode` if that breaks the contract.

Another policy (for example, comparing by the delegate's business identity) may be appropriate, but it must be **designed and tested consistently**. Do not automatically assume that delegating all three Object methods to the delegate is right for every system; two different proxies may share the same delegate while still needing distinct proxy identities.

### 7.2. Do Not Unconditionally Call `String.valueOf(proxy)` or `Arrays.deepToString(args)`

If `args[0]` is the proxy itself in `equals(proxy)`, a formatter might call `proxy.toString()`, triggering a nested invocation cycle. Even if it does not loop infinitely, the log will no longer consist of **one line per original call**.

A safe way to handle self-references:

```java
// Simple snippet inside a formatter.
if (argument == proxy) {
    out.append("<self>");
} else if (argument instanceof String[] array) {
    out.append(Arrays.toString(array));
} else {
    out.append(argument);
}
```

This snippet can still trigger `toString` on other objects, so a production-grade formatter may log only **type/identity**, redact sensitive data, or truncate depth. The complete runnable example also detects **other proxies** to limit re-entry.

## 8. Complete Java 17+ Example: Properly Reading `Method`/`proxy`/`args`

Create the file **`ProxyInvocationDemo.java`** with the **entire code** below. The program intentionally includes:

- Zero-argument methods: `ping()`, `size()`, `touch()`, and `fail()`.
- Method with one normal or `null` argument: `echo(String)`.
- Varargs method with 2, 0, or a null array: `join(String...)`.
- `Object` calls: `toString()`, `equals(Object)`, `hashCode()`.
- Returns of `String`, `int`, and `void`.
- A delegate that throws an exception to verify `InvocationTargetException` handling.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class ProxyInvocationDemo {
    public interface TaskService {
        String ping();
        String echo(String text);
        String join(String... values);
        int size();
        void touch();
        String fail();
    }

    public static final class RealTaskService implements TaskService {
        private int touches;

        @Override public String ping() {
            return "pong";
        }

        @Override public String echo(String text) {
            return text == null ? "<null>" : "echo:" + text;
        }

        @Override public String join(String... values) {
            return values == null ? "<null-array>" : String.join("|", values);
        }

        @Override public int size() {
            return 7;
        }

        @Override public void touch() {
            touches++;
        }

        @Override public String fail() {
            throw new IllegalStateException("delegate failed");
        }
    }

    public static final class LoggingHandler implements InvocationHandler {
        private final TaskService target;

        public LoggingHandler(TaskService target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            System.out.println("call " + method.getName()
                    + " owner=" + method.getDeclaringClass().getSimpleName()
                    + " argc=" + (args == null ? 0 : args.length)
                    + " args=" + describe(proxy, args)
                    + " varargs=" + method.isVarArgs()
                    + " proxy=" + Proxy.isProxyClass(proxy.getClass()));

            // Object methods have their own identity policy.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "TaskServiceProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            // Zero-arg methods have args=null, so normalize before delegating.
            Object[] safeArgs = args == null ? new Object[0] : args;
            try {
                return method.invoke(target, safeArgs);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }

        private static String describe(Object proxy, Object[] args) {
            if (args == null) return "<null>";

            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < args.length; i++) {
                if (i > 0) sb.append(", ");
                Object value = args[i];

                if (value == proxy) {
                    sb.append("<self>");
                } else if (value instanceof String[] a) {
                    sb.append(Arrays.toString(a));
                } else if (value != null
                        && Proxy.isProxyClass(value.getClass())) {
                    sb.append("<other-proxy>");
                } else {
                    sb.append(value);
                }
            }
            return sb.append("]").toString();
        }
    }

    public static void main(String[] args) {
        RealTaskService real = new RealTaskService();
        TaskService service = (TaskService) Proxy.newProxyInstance(
                TaskService.class.getClassLoader(),
                new Class<?>[]{TaskService.class},
                new LoggingHandler(real));

        System.out.println("ping=" + service.ping());
        System.out.println("echo=" + service.echo("Java"));
        System.out.println("echo null=" + service.echo(null));
        System.out.println("join many=" + service.join("a", "b"));
        System.out.println("join zero=" + service.join());
        System.out.println("join null-array="
                + service.join((String[]) null));
        System.out.println("size=" + service.size());

        service.touch();
        System.out.println("touches=" + real.touches);

        System.out.println("toString=" + service.toString());
        System.out.println("equals self=" + service.equals(service));
        System.out.println("equals null=" + service.equals(null));
        System.out.println("hash identity="
                + (service.hashCode() == System.identityHashCode(service)));

        try {
            service.fail();
        } catch (IllegalStateException ex) {
            System.out.println("fail=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }
}
```

Run in the directory containing the file, with JDK 17 or later:

```bash
javac ProxyInvocationDemo.java
java ProxyInvocationDemo
```

**Exact stdout verified by compiling and running the program on the JDK:**

```text
call ping owner=TaskService argc=0 args=<null> varargs=false proxy=true
ping=pong
call echo owner=TaskService argc=1 args=[Java] varargs=false proxy=true
echo=echo:Java
call echo owner=TaskService argc=1 args=[null] varargs=false proxy=true
echo null=<null>
call join owner=TaskService argc=1 args=[[a, b]] varargs=true proxy=true
join many=a|b
call join owner=TaskService argc=1 args=[[]] varargs=true proxy=true
join zero=
call join owner=TaskService argc=1 args=[null] varargs=true proxy=true
join null-array=<null-array>
call size owner=TaskService argc=0 args=<null> varargs=false proxy=true
size=7
call touch owner=TaskService argc=0 args=<null> varargs=false proxy=true
touches=1
call toString owner=Object argc=0 args=<null> varargs=false proxy=true
toString=TaskServiceProxy
call equals owner=Object argc=1 args=[<self>] varargs=false proxy=true
equals self=true
call equals owner=Object argc=1 args=[null] varargs=false proxy=true
equals null=false
call hashCode owner=Object argc=0 args=<null> varargs=false proxy=true
hash identity=true
call fail owner=TaskService argc=0 args=<null> varargs=false proxy=true
fail=IllegalStateException:delegate failed
```

### 8.1. Analyzing the Important Lines

- **`ping()`:** `argc=0 args=<null>`. The handler must not use `args.length` directly. `safeArgs` becomes an empty array when calling `method.invoke(target,safeArgs)` and returns `pong`.
- **`echo("Java")`:** `argc=1 args=[Java]`. `Method` specifies the parameter type is `String`; the handler receives a single-element array.
- **`echo(null)`:** `argc=1 args=[null]`, **different** from `args=<null>` of a zero-argument method. Only the first element holds a null value.
- **`join("a","b")`:** `method.isVarArgs()==true` yet `argc=1`. That is a `String[]` containing two elements, represented by the formatter as `[[a, b]]`.
- **`join()`:** still `argc=1`, the first element is `String[0]`; output `args=[[]]`. This is not a method call with 0 parameters in terms of signature.
- **`join((String[])null)`:** still `argc=1` but the single element is a null array, output `args=[null]`. The delegate has logic to handle it so it returns `<null-array>`.
- **`size()`:** the handler receives `args=null`, yet calling the delegate returns a primitive `int`; Reflection boxes it into `Integer` and then the proxy unboxes it back to `int` for the caller.
- **`touch()`:** the handler calls a void method; the delegate increments the counter. The result the handler gets from `Method.invoke` is null, yet outside we still see `touches=1`.
- **`toString/hashCode`:** methods belonging to `Object`, with no arguments; the handler returns according to the identity policy and does not call `proxy.toString()/hashCode()` on itself.
- **`equals(service)`:** a single-element array containing **the proxy itself**. The formatter detects the self-reference and prints `<self>` to avoid triggering nested `toString` calls.
- **`fail()`:** the delegate throws `IllegalStateException`, Reflection wraps it; the handler unwraps it so the caller sees the exact `IllegalStateException` with the original message.

### 8.2. Why Does the Log Record Both `owner` and `proxy=true`?

`owner=TaskService` describes where the `Method` received by the handler is declared. `proxy=true` uses `Proxy.isProxyClass(proxy.getClass())` to confirm the receiver belongs to a JDK-generated proxy class. Both pieces of information can be true at the same time because **the runtime receiver** and **the method's declaring class** are two different concepts.

### 8.3. Why Is a Separate `target` Variable Needed?

`target` points to `RealTaskService`, which is the object containing the business logic. The handler only calls `method.invoke(target,safeArgs)`; this ensures the call goes to the real implementation instead of looping back to the proxy receiver.

In applications with multiple interfaces or complex routing, a `Method` may not fit every delegate: you must choose a delegate that implements the right declaring interface (or on which the method can be invoked) before forwarding. Otherwise, `Method.invoke` may throw `IllegalArgumentException` due to an incompatible receiver.

## 9. Distinguishing Varargs from Zero-Argument Methods

This is a particularly common source of bugs when inspecting `Object[] args`.

For the method:

```java
String join(String... values);
```

Java compiles it into a method with **one `String[]` parameter**, marking the method as varargs. When the caller writes:

```java
service.join();
service.join("x");
service.join("x", "y");
service.join((String[]) null);
```

the handler still receives `method.getParameterCount()==1`, `method.isVarArgs()==true`, and normally `args.length==1`. The element `args[0]` is a `String[]` array with 0, 1, 2 elements, or null respectively.

One way to illustrate this:

```text
join()                    -> args = [String[0]]
join("x")                 -> args = [String[1]{"x"}]
join("x", "y")            -> args = [String[2]{"x","y"}]
join((String[]) null)     -> args = [null]
ping()                    -> args = null
echo(null)                -> args = [null]
```

**Note:** The representation above only describes the structure, not the output of `Arrays.toString`; the actual program output is already in section 8.

If a framework wants to measure **the number of varargs elements**, it must check `method.isVarArgs()`, identify the last array, and process the value `args[args.length-1]` according to its array type. **You cannot use `args.length` as the number of varargs elements**.

Example snippet specifically for `String...`:

```java
if (method.isVarArgs() && args != null && args.length > 0) {
    Object last = args[args.length - 1];
    if (last instanceof String[] strings) {
        System.out.println("vararg elements=" + strings.length);
    } else if (last == null) {
        System.out.println("vararg array is null");
    }
}
```

This snippet **does not cover every kind of varargs**: `int...` uses `int[]`, `Object...` uses `Object[]`, and generic varargs may erase to other array types. For a general-purpose framework, use `method.getParameterTypes()` to determine **the last array type**, then consider `java.lang.reflect.Array.getLength(...)`/`Array.get(...)` after null checks.

### 9.1. Passing Null as a Single Argument Can Be Ambiguous

If a method takes `String...` and the caller writes `join(null)`, the compiler may warn because the call matches either the **null array** interpretation or **one null element**. Write it explicitly:

```java
join((String[]) null); // Passes the parameter array itself as null.
join((String) null);   // Passes a single String element whose value is null.
```

The two calls produce different `args` structures. In the `TaskService` example, `join((String[])null)` is handled safely; whereas `join((String)null)` will create an array containing one null, and `String.join` in the implementation has its own behavior (do not infer the output without testing).

## 10. Default Methods, Overloads, and Multiple Interfaces

### 10.1. Default Methods Do Not Run Automatically Just Because an Implementation Exists in the Interface

When a proxy implements an interface with a **default method**, the call still goes through `InvocationHandler.invoke`. If the handler wants to execute the default implementation itself on the proxy, Java 17+ provides the API:

```java
InvocationHandler.invokeDefault(proxy, method, args);
```

`method.isDefault()==true` is required and the method must belong to an appropriate interface. Avoid calling `method.invoke(proxy,args)` to run the default body, as it can call back into the handler.

A **standalone runnable** example saved as **`ProxyDefaultDemo.java`**:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyDefaultDemo {
    public interface Greeting {
        default String hello() {
            return "hello-default";
        }
    }

    public static void main(String[] args) {
        Greeting greeting = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[]{Greeting.class},
                (proxy, method, arguments) -> {
                    System.out.println("isDefault=" + method.isDefault()
                            + " argc=" + (arguments == null
                                    ? 0 : arguments.length));

                    if (method.isDefault()) {
                        return InvocationHandler.invokeDefault(
                                proxy, method,
                                arguments == null
                                        ? new Object[0] : arguments);
                    }

                    throw new UnsupportedOperationException(
                            method.toString());
                });

        System.out.println("result=" + greeting.hello());
    }
}
```

Run commands:

```bash
javac ProxyDefaultDemo.java
java ProxyDefaultDemo
```

Exact stdout:

```text
isDefault=true argc=0
result=hello-default
```

Takeaway from the example: the default method `hello()` still has `arguments==null` because it has no parameters. `invokeDefault` uses an empty array when forwarding. This is an **intentional** choice to run the interface's default implementation; there is no need to use it if the handler already has a delegate implementing the appropriate method.

### 10.2. Multiple Interfaces with the Same Signature

`Proxy.newProxyInstance` can accept multiple interfaces. If the interfaces have methods with the same name and parameter list, the proxy cannot distinguish intent just from which interface the caller cast the receiver to at each call site. By the `Proxy` contract, the method dispatched to the handler may be chosen based on **the order of interfaces** in the proxy list, rather than always matching the interface appearing in the caller's static type.

Therefore:

- Do not assume `method.getDeclaringClass()` is always the interface that the caller code cast to.
- When designing dispatch based on `Method`, account for signature collisions and the proxy's interface order.
- The `equals`, `hashCode`, and `toString` methods have special rules and are normally presented with declaring class `Object.class`.
- If interfaces have methods with the same name+parameter types but incompatible return types, proxy creation may fail.

For complex multi-interface cases, it is best to build a **consistent routing table** from valid signatures to desired behavior, rather than inferring from the runtime receiver of each call.

### 10.3. Different Overloads Must Be Distinguished Completely

Example:

```java
interface Resolver {
    String resolve(String name);
    String resolve(long id);
}
```

Both methods have `getName()=="resolve"` but different `getParameterTypes()`. If a handler switches only by name, it can send the wrong argument to a delegate. You can identify them using the full parameter list:

```java
// Snippet inside the handler, not a standalone program.
if (method.getName().equals("resolve")
        && Arrays.equals(method.getParameterTypes(),
                         new Class<?>[]{String.class})) {
    // resolve(String) branch.
}
```

In production, better designs depend on the framework: mapping by `Method`, normalized signatures, or metadata prepared when building the proxy. **Do not** merge all methods with the same name and erase overloads.

## 11. Errors and Scenarios to Diagnose

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `NullPointerException` when accessing `args.length` | Zero-argument method, `args==null` | Guard `args==null` or use `getParameterCount()` first |
| Zero-argument method treated by handler as one null argument | Confusing `args==null` and `args[0]==null` | Distinguish the structures in section 5 |
| Varargs `join()` logged as 0 parameters | Using the varargs element count instead of parameter count | `Method.getParameterCount()==1`, `args[0]` is an empty array |
| `StackOverflowError` or endless recursive logs | Calling `method.invoke(proxy,args)`/`proxy.toString()` from the handler | Use the real delegate; log identity instead of proxy's `toString` |
| `IllegalArgumentException: object is not an instance of declaring class` | Forwarding an interface method to a delegate that does not implement the matching interface | Identify the right delegate and signature |
| `UndeclaredThrowableException` | Handler propagates a checked exception not permitted by the method signature to the caller | Unwrap `InvocationTargetException`; respect interface checked exceptions |
| `ClassCastException` or `NullPointerException` at proxy return | Handler returns the wrong wrapper or `null` for a primitive-return method | Ensure the return type matches `Method.getReturnType()` |
| `equals`/`hashCode` behave inconsistently | One method uses identity, the other uses business identity | Design both consistently |
| `toString` triggers multiple handler calls | Logger stringifies a receiver/args containing the proxy | Switch to an identity-safe formatter |
| Default method does not run as expected | Handler blocks/does not forward the default body | Use an explicit policy; consider Java 17+ `InvocationHandler.invokeDefault` |
| Overload misclassified | Dispatching solely by `getName()` | Combine name and parameter type list |
| Multiple interfaces with colliding signatures at runtime | Treating `declaringClass` as the interface the caller cast to | Check the proxy's interface order and dispatch policy |
| Unable to create proxy | Class loader cannot see the interface, unsuitable interface, or package/module rules | Check `Proxy.newProxyInstance`, class loader, interface list, modules |
| Handler sees null without knowing which case it is | Logs do not record metadata and `args` structure | Log `getParameterCount`, `isVarArgs`, null status, and last array type |

### 11.1. Ordered Log-Reading Checklist

For an issue in `InvocationHandler`, proceed in order:

1. Determine whether this is a JDK proxy using `Proxy.isProxyClass(proxy.getClass())`, without hard-coding the proxy class name.
2. Log `method.getName()`, `method.getDeclaringClass()`, `method.getParameterTypes()`, and `method.getReturnType()`.
3. Log **`args==null`** and **`args.length` when non-null** separately. Do not call `Arrays.deepToString(args)` on objects capable of re-entering the handler without protection.
4. If `method.getDeclaringClass()==Object.class`, apply the policy for `equals/hashCode/toString`.
5. If `method.isVarArgs()`, check the type/value of **the last array**, do not interpret `args.length` as the number of varargs elements.
6. If forwarding, select the right delegate, then normalize `args` and call `method.invoke(delegate,safeArgs)`.
7. If the delegate throws an exception, unwrap `InvocationTargetException`; if the caller sees `UndeclaredThrowableException`, check checked exceptions and the interface signature.
8. If the return type is primitive, verify the handler returned a valid wrapper rather than null.
9. Also test null arguments, zero arguments, empty varargs, and `equals(proxy)` to avoid hidden bugs in simple scenarios.

### 11.2. Calls You Should Not Use Directly for Debugging

`System.out.println(proxy)` or `String.format("proxy=%s", proxy)` inside the handler can call `proxy.toString()`. Putting `proxy` into a `HashMap` structure can also cause `hashCode()`/`equals()` to run through the handler. Use `System.identityHashCode(proxy)` or only log `proxy.getClass()` to separate metadata observation from business logic.

Do not call `method.invoke(proxy, ...)` just to "see the result" of the method the handler is currently processing; as explained, doing so usually leads to a self-calling loop.

## 12. Guide to Testing a Handler Before Using It in a Framework

A small test suite should cover meaningfully different cases, not just the happy path:

| Test case | Example call | Result the handler must recognize |
| --- | --- | --- |
| Zero-argument returning reference | `ping()` | `getParameterCount()==0`, `args==null`, returns string |
| Zero-argument returning primitive | `size()` | `args==null`, return must be compatible with `int` |
| Zero-argument returning void | `touch()` | `args==null`, delegate runs even though return is null |
| One normal parameter | `echo("Java")` | `args.length==1` and `args[0]="Java"` |
| One null parameter | `echo(null)` | `args.length==1` and `args[0]==null` |
| Varargs with elements | `join("a","b")` | `isVarArgs()==true`, `args.length==1`, `args[0]` is `String[2]` |
| Varargs with no elements | `join()` | `args.length==1`, `args[0]` is `String[0]` |
| Varargs null array | `join((String[])null)` | `args.length==1`, `args[0]==null` |
| Object `toString` | `proxy.toString()` | `Method` of `Object`, `args==null`, no re-entry |
| Object `equals` | `proxy.equals(proxy)` | `args.length==1`, first element is the proxy itself |
| Object `hashCode` | `proxy.hashCode()` | `args==null`, does not recursively call proxy hashCode |
| Exception from delegate | `fail()` | Business exception reaches caller after unwrapping |
| Default method | `hello()` in default interface | Handler receives `Method.isDefault()==true`, chooses execution policy |
| Overload | `resolve(String)` and `resolve(long)` | Does not merge two methods just because they share a name |

If a framework creates proxies from user interfaces, it should test **both kinds of callers**: code calling through the interface and code triggering indirect calls via logging/collections. Many recursion bugs only appear when logging calls `toString()` or a collection needs `hashCode()`, and do not appear when testing a pure business method.

## 13. Practice Exercises and Solutions

**Exercise 1.** `interface Job { void run(); }`. The handler writes `System.out.println(args.length);`. What happens when calling `proxy.run()`?  
**Solution:** `args==null` because `run()` has no parameters, so `args.length` throws `NullPointerException`. Write `args == null ? 0 : args.length` or use `method.getParameterCount()` to get the declared parameter count.

**Exercise 2.** `interface Job { void run(String value); }`. The caller calls `proxy.run(null)`. Is `args` null or a single-element array?  
**Solution:** It is a single-element array with `args[0]==null`. This is **different** from a zero-argument method.

**Exercise 3.** `interface Job { void run(String... values); }`. Does calling `proxy.run()` make `args==null`?  
**Solution:** No. The method has one `String[]` parameter, so `args` has one element which is an empty array in a normal varargs call.

**Exercise 4.** Inside a handler, `return method.invoke(proxy,args);` is used to run business logic. Why is this dangerous?  
**Solution:** `proxy` is the JDK-generated proxy receiver; calling a method on it can repeatedly loop back into the same handler. Forward to the real delegate or handle the call with another policy.

**Exercise 5.** A logger inside the handler uses `"receiver=" + proxy`. Why can this cause a `StackOverflowError`?  
**Solution:** String concatenation calls the proxy's `toString()`; `toString` enters the handler again, logs the receiver again... Use identity-safe logging.

**Exercise 6.** The handler forwards `Method.invoke(delegate, safeArgs)`, and the delegate throws `IllegalStateException`. What needs to be handled?  
**Solution:** Reflection wraps it in `InvocationTargetException`; catch the wrapper and `throw ex.getCause()` to preserve the original exception.

**Exercise 7.** The handler returns `null` for `int count()`. Why can this fail?  
**Solution:** The proxy needs to unbox the result to `int`; `null` cannot be unboxed, leading to `NullPointerException`. A valid `Integer` wrapper must be returned.

**Exercise 8.** How do you distinguish `get(String)` and `get(long)` when both have `getName()=="get"`?  
**Solution:** Also use `method.getParameterTypes()` or exact `Method` metadata, do not dispatch solely by name.

**Exercise 9.** A proxy implements two interfaces that both declare `void refresh()`. Is `method.getDeclaringClass()` always the interface type the caller cast to?  
**Solution:** No. JDK proxies have rules for selecting the method when multiple interfaces share a signature; the order of interfaces when creating the proxy can determine which `Method` is presented to the handler.

**Exercise 10.** When `method.isDefault()==true`, can you call `method.invoke(proxy,args)` to run the default body?  
**Solution:** You should not; calling the method back on the proxy can re-enter the handler. Java 17+ allows using `InvocationHandler.invokeDefault(proxy, method, normalizedArgs)` in appropriate cases.

**Exercise 11.** Why is `System.identityHashCode(proxy)` safer than `proxy.hashCode()` inside a handler?  
**Solution:** `System.identityHashCode` gets the identity hash code without calling the overridden `hashCode` on the proxy; `proxy.hashCode()` goes through the handler and can cause recursion.

**Exercise 12.** Why is `method.getDeclaringClass()==TaskServiceImpl.class` not the way to identify all business calls?  
**Solution:** JDK proxies use method metadata from interfaces/`Object`, not from the implementation class by default. The delegate class is where the handler decides to delegate to.

## 14. Summary

A resilient handler must follow these principles:

- **`proxy` is the proxy receiver**, not the delegate, and should not be unconditionally stringified.
- **`Method` describes the method dispatched by the proxy**, usually declared on an interface or `Object`; read `name`, `parameterTypes`, `returnType`, `isVarArgs`, `isDefault`, and owner when needed.
- **`args==null` for zero-argument methods**. Check for null before counting or iterating. Do not confuse it with an array containing **one null element**.
- **Varargs is a single array parameter at bytecode level**. `join()` does not turn the handler's `args` into null if the method declares `String...`.
- **Handle `equals/hashCode/toString` separately** under a consistent policy; do not call back into the proxy causing recursion.
- **When a delegate exists**, use `method.invoke(delegate, normalizedArgs)` and unwrap `InvocationTargetException`. Do not call `method.invoke(proxy,...)` to self-forward.
- **Check return types and checked exceptions**. Primitive-return methods need a valid wrapper; checked exceptions outside the declaration may be wrapped.
- **For default methods**, you can call `InvocationHandler.invokeDefault` on Java 17+ if you want to execute the default body.

In short, before writing any code that processes `args`, always ask yourself: *How many parameters does this method declare? Is the last parameter a varargs array? Is the current receiver the proxy or the delegate?* Answering those three questions correctly will eliminate most dynamic proxy handler bugs.

### Official Documentation

- [Oracle Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): contract of `invoke`, the three parameters, `args=null` when there are no arguments, and `invokeDefault`.
- [Oracle Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): proxy creation mechanism, `Object` methods, class loaders, and signature collisions between interfaces.
- [Oracle Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getDeclaringClass`, `getParameterTypes`, `isVarArgs`, `isDefault`, and `Method.invoke`.
- [Oracle Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper for exceptions thrown by the target method when invoked via Reflection.
- [Oracle Java SE 17 — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): case where the proxy wraps a checked exception outside the method signature.
