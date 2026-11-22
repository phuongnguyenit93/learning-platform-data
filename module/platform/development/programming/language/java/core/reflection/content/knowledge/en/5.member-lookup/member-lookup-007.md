# Why Doesn't `getMethod` Automatically Resolve Overloads Like the Compiler?

## 1. Two Operations with Different Purposes

**Overloading** means multiple methods sharing the same name with different parameter type lists. For a call `obj.send(value)` in Java code, the **compiler** must determine one appropriate overload based on the *compile-time* types of the arguments and the rules of the language.

By contrast, `Class.getMethod(String name, Class<?>... parameterTypes)` is a Reflection API for **looking up a public method with a specified name and declared parameter type list**. The `Class<?>` objects passed describe the method signature **to search for**; they are not input values for automatically picking an overload.

Suppose there are `send(int)` and `send(long)`:

- `send((short) 7)` in source code selects `send(int)`, thanks to primitive widening conversion (`short` to `int`).
- `SomeClass.class.getMethod("send", short.class)` searches strictly for `send(short)`. If that signature is not declared, it throws `NoSuchMethodException`, even though `send(int)` accepts a `short` value when called directly.

**Exact signature lookup** and **overload call resolution** are two different problems.

## 2. How Does the Compiler Resolve Overloads?

The compiler has information about the method name, argument count, **the static type of each expression**, visible methods, generic information, and call context. According to the Java Language Specification, the method selection process has main phases:

1. Try methods with a fixed number of parameters, **without boxing/unboxing**, though primitive widening (`short → int`) or reference widening (`Integer → Number`) can be used.
2. If no applicable method has been found, additionally consider boxing/unboxing and conversions allowed in method invocations.
3. If still not found, consider `varargs` calls with variable argument counts.
4. At the first phase with suitable candidates, pick the *most specific* overload per Java rules; if a unique one cannot be chosen, report an **ambiguous** error.

Actual rules also account for inheritance, generic type inference, and accessibility; they cannot be replaced solely by `Class.isAssignableFrom()`.

**Static types are not always the same as runtime types.** Given `send(Object)`, `send(String)`, and declaration `Object x = "hello";`, the call `send(x)` is compiled to `send(Object)`, because the static type of `x` is `Object`. Meanwhile, `x.getClass()` returns `String.class`: using the runtime class to guess an overload can yield a different result than the compiler.

## 3. What Does `Class.getMethod` Match?

API form:

~~~java
Method method = SomeClass.class.getMethod(
    "methodName",
    FirstParameterType.class,
    SecondParameterType.class
);
~~~

This is a **syntax illustration**, not a complete Java program. `getMethod` matches the **name** and **declared parameter types in exact order**. It performs no type conversion, inspects no argument values, and does not pick the "closest" overload. For example:

| Lookup | Required Match |
| --- | --- |
| `getMethod("send", int.class)` | Exactly `send(int)`. |
| `getMethod("send", Integer.class)` | Exactly `send(Integer)`, distinct from `send(int)`. |
| `getMethod("send", Number.class)` | Exactly `send(Number)`, does not fall back to `send(Object)`. |
| `getMethod("batch", String[].class)` | Matches `batch(String...)`, because a varargs parameter is actually an array. |
| `getMethod("batch", String.class, String.class)` | Does not match `batch(String...)`, even though source code can call `batch("a", "b")`. |

`getMethod` searches **`public`** methods, including eligible inherited public methods. `getDeclaredMethod` still requires exact parameter types, but searches only methods declared directly in that class/interface, including non-public members. If the signature is not found, `NoSuchMethodException` is thrown.

With generics, Reflection sees the signature after **type erasure**: a method `accept(List<String>)` must usually be looked up with `List.class`; Java has no `List<String>.class` expression. The `getMethod` API also does not accept the return type as a selection parameter. Sometimes the compiler generates bridge/synthetic methods; when traversing method lists, inspect `isBridge()` and `isSynthetic()`.

## 4. Complete Java 17+ Illustrative Program

Save as `ReflectionOverloadDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectionOverloadDemo {
    public void send(int value) {
        System.out.println("send(int): " + value);
    }

    public void send(long value) {
        System.out.println("send(long): " + value);
    }

    public void send(Integer value) {
        System.out.println("send(Integer): " + value);
    }

    public void send(Number value) {
        System.out.println("send(Number): " + value);
    }

    public void send(Object value) {
        System.out.println("send(Object): " + value);
    }

    public void batch(String... items) {
        System.out.println("batch: " + Arrays.toString(items));
    }

    public static void main(String[] args) throws Exception {
        ReflectionOverloadDemo target = new ReflectionOverloadDemo();
        short n = 7;

        // The compiler chooses the overload from the static type of the call.
        target.send(n);
        target.send(Integer.valueOf(7));
        target.send((Number) Integer.valueOf(7));

        // There is no exact signature send(short).
        try {
            ReflectionOverloadDemo.class.getMethod("send", short.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No send(short)");
        }

        // Reflection requires us to specify the exact signature.
        Method intMethod =
                ReflectionOverloadDemo.class.getMethod("send", int.class);
        intMethod.invoke(target, 7);

        Method numberMethod =
                ReflectionOverloadDemo.class.getMethod("send", Number.class);
        numberMethod.invoke(target, Integer.valueOf(7));

        try {
            ReflectionOverloadDemo.class.getMethod("send", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No send(String)");
        }

        // String... is declared as String[].
        Method batchMethod =
                ReflectionOverloadDemo.class.getMethod("batch", String[].class);
        batchMethod.invoke(target, (Object) new String[]{"a", "b"});
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac ReflectionOverloadDemo.java
java ReflectionOverloadDemo
~~~

Exact stdout:

~~~text
send(int): 7
send(Integer): 7
send(Number): 7
No send(short)
send(int): 7
send(Number): 7
No send(String)
batch: [a, b]
~~~

Observations:

- Variable `n` has type `short`, so a normal Java call selects `send(int)`, yet looking up `getMethod("send", short.class)` still fails.
- `int.class` differs from `Integer.class`. The value `7` passed to `Method.invoke(Object, Object...)` is boxed into an `Integer`, and then Reflection can unbox it for the selected `int` parameter.
- `numberMethod` is already fixed to `send(Number)`. Passing an `Integer` argument to `invoke` does not switch it to the `send(Integer)` overload.
- `String... items` becomes a `String[]` parameter. Casting `(Object) new String[]{...}` forces the `invoke` call to receive **one array argument** instead of mistaking its elements for the argument list of `invoke`.

## 5. Why Does `Method.invoke` Accept Some Conversions?

There are two separate steps:

~~~text
Class.getMethod("send", int.class)
            |
            v
 Method representing send(int)   (exact overload selected)
            |
            v
 method.invoke(target, value) (invokes the selected Method)
~~~

`Method.invoke` **does not run overload resolution**. It only validates/converts arguments against the parameter types of the **Method currently held**. Per the JDK, Reflection can unbox and apply valid primitive widening at execution time; invalid primitive *narrowing* conversions result in `IllegalArgumentException`. Having a varargs target method also does not cause `Method.invoke` to automatically pack the caller's arguments according to Java syntax. If the target method itself throws an exception, Reflection usually wraps it in `InvocationTargetException`.

Therefore, `invoke` can call `send(int)` with an `Integer` containing `7`, **but `getMethod("send", Integer.class)` does not thereby resolve to `send(int)`**.

## 6. Proper Usage in Practice

**When the API is already known:** write the declared parameter type list explicitly. If a method takes `int`, use `int.class`; if `Number`, use `Number.class`; if `String...`, use `String[].class`. Then call `invoke` with the exact argument count and compatible values.

**When dispatching from dynamic data:** you can iterate `getMethods()`, filter by name, and build an overload selector yourself. However, a sufficiently accurate selector must understand primitive/wrapper, widening, reference hierarchy, `null`, varargs, generic/bridge methods, and ambiguous overloads. Using only `arg.getClass()` or `isAssignableFrom()` is not enough. For JSON, HTTP, or configuration, a more controllable approach is to explicitly define operation names and valid signatures in the data contract.

**When using Method Handles:** `MethodHandles.Lookup.findVirtual` or `findStatic` also requires a specified `MethodType`; it is not an implicit compiler-equivalent overload resolver either.

### Common Mistakes

1. Using `Integer.class` to look up `method(int)`, or `int.class` to look up `method(Integer)`.
2. Calling `arg.getClass()` as if it were the variable's static type: primitives get boxed; a `null` argument has no `getClass()`.
3. Looking up `method(String...)` with multiple `String.class` arguments instead of one `String[].class`.
4. Using `getMethod` to look up a `private` method. `getDeclaredMethod` can find non-public declared methods, though invoking may require access permissions; `setAccessible` is also subject to Java Platform Module System limits.
5. Taking the "first method" from `getMethods()`: array order is not used as overload priority.

## 7. Self-Check Questions

- Given only `f(long)`: does `f(3)` compile? **Yes**, due to `int → long`. Then does `getMethod("f", int.class)` find it? **No**, because no `f(int)` exists.
- Given `f(String)` and `f(Integer)`: can `f(null)` pick a unique overload? **No**, the call is ambiguous because neither parameter type is more specific than the other; Reflection must explicitly specify `String.class` or `Integer.class`.
- Obtain `getMethod("f", String.class)` and call `invoke(instance, new Object[]{null})`: can it switch to `f(Integer)`? **No**. `Method` already represents `f(String)`.

**Takeaway:** the compiler resolves **a call** based on expression types and Java rules; `getMethod` looks up **an exact method signature** from the `Class` list you provide. `invoke` only executes the already-selected method.

### Further Reading in Standard Documentation

- [JDK 17: `Class.getMethod` and `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getMethod(java.lang.String,java.lang.Class...))
- [JDK 17: `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java Language Specification §15.12: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12)