# Distinguishing Method Lookup Rules from Argument Conversion Rules in Reflection Calls

In Java Reflection, **finding a method** and **invoking the found method** are two phases with different type rules:

1. **Lookup:** `Class.getMethod(name, parameterTypes...)` or `Class.getDeclaredMethod(name, parameterTypes...)` identifies a `Method` by **name and declared parameter type list**, within the appropriate public/declared scope. The parameter types passed to the lookup method are `Class<?>` objects. Java does not automatically find overloads via `byte -> long` conversion, `int -> Integer` boxing, or `Integer -> Number` inheritance relationships.
2. **Invocation:** Once you have a `Method` object, `Method.invoke(receiver, args...)` checks access permissions, the receiver, the argument count, and **the convertibility of actual arguments** to the formal parameter types. Under the right conditions, Reflection allows **unboxing** wrapper values to primitives, **widening primitive conversion**, and assigning a reference object to a compatible reference type. It does not allow narrowing primitive conversion.

This difference explains why `getMethod("work", byte.class)` cannot find `work(long)`, whereas `getMethod("work", long.class).invoke(obj, Byte.valueOf((byte) 7))` can run successfully.

## 1. Lookup phase: selecting a method by declaration

For example, a class with two overloads:

```java
class Service {
    public void process(int value) {}
    public void process(long value) {}
}
```

This snippet illustrates a class definition. With `Service.class`:

```java
Method intMethod = Service.class.getMethod("process", int.class);
Method longMethod = Service.class.getMethod("process", long.class);
```

The two calls request `process(int)` and `process(long)` exactly. If you replace `int.class` or `long.class` with `byte.class`, `getMethod` does not pick the "nearest candidate" for the caller's convenience. If there is no `process(byte)`, the result is **`NoSuchMethodException`**.

**The types in the lookup call are the formal parameter types**, not a runtime argument being prepared to pass to the method. Therefore:

- `int.class` differs from `Integer.class`: there is no boxing/unboxing to find a method.
- `long.class` differs from `int.class`: there is no widening to find a method.
- `Number.class` differs from `Integer.class`: lookup does not automatically substitute types in the parameter list based on inheritance.
- `String[].class` differs from `String.class`: a varargs parameter declared as `String...` has the array type `String[]` in metadata.
- Both parameter order and **count** must be exact: `calculate(int, long)` differs from `calculate(long, int)`.

### getMethod and getDeclaredMethod differ in scope

| API | Methods looked up |
| --- | --- |
| `getMethod(name, parameterTypes...)` | `public` methods visible through the target type, including applicable inherited methods |
| `getDeclaredMethod(name, parameterTypes...)` | Methods declared directly on that class/interface itself, including `private` or package-private ones; does not walk up to the superclass |

Both still use the name and declared parameter type list to find a method, without performing overload resolution as the compiler does for a normal Java call. `getDeclaredMethod` can **retrieve metadata** for a private method, but retrieving metadata does not automatically grant permission to `invoke`; access permissions are checked later.

**Do not pass the return type to `getMethod` or `getDeclaredMethod`.** The `getReturnType()` result is metadata read *after lookup*. For some class files with bridge methods or methods having the same name/parameter list but different return types, the API has its own selection rules based on return type specificity; therefore, advanced bytecode analysis tools also need to check `Method.isBridge()` and `isSynthetic()`. This does not turn Reflection lookup into an automatic argument casting mechanism.

### Do not confuse with compile-time overload resolution

In normal Java code:

```java
byte b = 7;
new Service().process(b);
```

This snippet is in the context of `Service` above. The **compiler** considers applicable overloads according to the Java Language Specification; in the case of `process(int)` and `process(long)` here, it selects `process(int)` because `int` is the more specific candidate for `byte`.

In Reflection, you cannot pass an expression `b` into `getMethod` for the compiler to choose automatically. The Reflection user **must decide which method to retrieve** using `Class<?>...` first, and then `invoke` on the selected method.

## 2. Invocation phase: Method.invoke performs conversions for arguments

Main syntax:

```java
Object result = method.invoke(receiver, arg1, arg2);
```

This is an illustrative snippet, assuming valid `Method method`, `receiver`, `arg1`, `arg2` already exist; the code needs to handle Reflection exceptions.

`Method.invoke(Object obj, Object... args)` has two kinds of parameters at the Reflection layer:

- `obj` is the **receiver** of an instance method; for a static method, the receiver is ignored so `null` is usually passed.
- `args` are the values used for the method's formal parameters. The number of values must match, and each value must be convertible to the corresponding formal parameter type.

Because `invoke` accepts `Object...`, when passing a primitive value directly in Java code calling `invoke`, the **compiler boxes that value** to place it into the `Object[]` array. Then `Method.invoke` processes the wrapper object and applies permitted conversions to convert it to the target method's primitive parameter type.

For example, if `method` represents `process(long)`, the following calls can all be type-valid:

```java
method.invoke(receiver, Byte.valueOf((byte) 7));
method.invoke(receiver, Integer.valueOf(8));
method.invoke(receiver, Long.valueOf(9L));
```

They can use `Byte`, `Integer`, `Long` wrapper values because unboxing and, if needed, primitive widening bring them to `long`. However, `Double` or `Float` cannot be passed to a `long` parameter via narrowing.

Importantly, **`invoke` does not search for another overload** when receiving arguments. Once `Method` points to `process(long)`, that exact method is invoked (with dynamic dispatch considered for overrides), even if the same class also has `process(int)` which might better fit some value type.

## 3. Complete Java 17+ example: proving lookup and invocation differ

Create the file `ReflectionLookupDemo.java`:

```java
import java.lang.reflect.Method;

public class ReflectionLookupDemo {
    public static class Service {
        public String describe(int v) {
            return "int:" + v;
        }

        public String describe(long v) {
            return "long:" + v;
        }

        public String accept(Number value) {
            return "Number:" + value;
        }

        public String join(String... values) {
            return String.join("/", values);
        }

        public int twice(int value) {
            return value * 2;
        }
    }

    public static void main(String[] args) throws Exception {
        Service s = new Service();
        Class<?> type = Service.class;

        Method m = type.getMethod("describe", long.class);
        System.out.println(
                "lookup(long)=" + m.getParameterTypes()[0].getSimpleName()
        );

        try {
            type.getMethod("describe", byte.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup(byte)=not found");
        }

        System.out.println(
                "invoke Byte->long=" + m.invoke(s, Byte.valueOf((byte) 7))
        );
        System.out.println(
                "invoke Integer->long=" + m.invoke(s, Integer.valueOf(8))
        );

        try {
            m.invoke(s, Double.valueOf(9.0));
        } catch (IllegalArgumentException e) {
            System.out.println("invoke Double->long=rejected");
        }

        Method n = type.getMethod("accept", Number.class);
        System.out.println(
                "invoke Integer->Number=" + n.invoke(s, Integer.valueOf(5))
        );

        try {
            type.getMethod("accept", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup accept(Integer)=not found");
        }

        Method v = type.getMethod("join", String[].class);
        System.out.println(
                "join(array)=" + v.invoke(s, (Object) new String[] {"a", "b"})
        );

        try {
            v.invoke(s, "a", "b");
        } catch (IllegalArgumentException e) {
            System.out.println("join(elements)=rejected");
        }

        Method twice = type.getMethod("twice", int.class);
        Object result = twice.invoke(s, Integer.valueOf(11));
        System.out.println(
                "return=" + result
                + ",type=" + result.getClass().getSimpleName()
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ReflectionLookupDemo.java
java ReflectionLookupDemo
```

Output:

```text
lookup(long)=long
lookup(byte)=not found
invoke Byte->long=long:7
invoke Integer->long=long:8
invoke Double->long=rejected
invoke Integer->Number=Number:5
lookup accept(Integer)=not found
join(array)=a/b
join(elements)=rejected
return=22,type=Integer
```

Analysis:

1. `getMethod("describe", long.class)` finds the exact `describe(long)` overload. `getMethod("describe", byte.class)` does **not** automatically apply `byte -> int` or `byte -> long`; both remain parameter types different from `byte`.
2. After retrieving `describe(long)`, `invoke` with `Byte` or `Integer` succeeds thanks to unboxing plus widening; the selected method is still the overload taking **`long`**, as proven by the strings `long:7` and `long:8`.
3. `Double` is incompatible with the formal parameter `long`; `invoke` throws `IllegalArgumentException`, which the program catches and prints clearly.
4. `getMethod("accept", Number.class)` finds the exact method declaring `Number`, while `invoke` accepts `Integer` because it is a compatible subtype. Looking up with `Integer.class` does not select `accept(Number)` instead.
5. The `String... values` parameter of the `join` method is reflected as **`String[]`**. `invoke(s, (Object) new String[] {"a", "b"})` passes a single array argument to the method and returns `a/b`; `invoke(s, "a", "b")` passes two separate arguments and is rejected because the method declares only **one** formal parameter of type `String[]`.
6. `twice(int)` returns primitive `int`, but `Method.invoke` returns `Object`, so the return value is **boxed** into `Integer`. This is the **result rule of invoke**, distinct from method selection and argument conversion.

The example intentionally catches two different kinds of errors: `NoSuchMethodException` occurs when **lookup fails to match**, whereas `IllegalArgumentException` occurs when you already have a `Method` but **the invocation arguments are incompatible**.

## 4. Workflow for selecting and invoking a method properly

When building a dynamic method invocation tool, clearly separate the decision of *selecting a method* from the step of *performing the invocation*:

1. **Determine scope:** search only declared methods or also inherited public methods; check module/access context.
2. **Select target method:** based on name and **formal parameter types** list. If you must handle overloads yourself, define a candidate policy and conversion priority; do not rely on the ordering of `getMethods()`.
3. **Prepare receiver:** `null` for static methods or an appropriate instance for instance methods.
4. **Prepare arguments:** count matches formal parameters; primitives accept wrappers that can unbox/widen; references accept assignment-compatible objects or `null`; a target method's formal varargs receives an appropriate array.
5. **Call `invoke` and handle errors:** distinguish lookup mismatch, lack of access permission, invalid conversion, and exceptions from the target method.
6. **Handle result:** `invoke` returns `Object`; primitive results are boxed, `void` returns `null`. If a specific type is needed, cast/check before using.

When implementing a custom overload resolver, consider `null` with multiple reference overloads, interface/superclass distances, primitive widening, boxing/unboxing, varargs, and ambiguity. The Java compiler has fairly complex overload selection rules; Reflection does not "re-run the compiler" on runtime arguments, so writing a manual resolver using only `getName()` and `getParameterCount()` easily picks the wrong method.

## 5. Self-check questions

1. A class only declares `work(long)`. Can `getMethod("work", int.class)` find it? **No.** Lookup requires the exact `long.class` formal parameter.
2. After obtaining the `Method` for `work(long)`, can you `invoke` it with `Integer.valueOf(3)`? **Yes.** `Integer` unboxes to `int`, then widens to `long`.
3. Can you `invoke` with `Double.valueOf(3.0)` for `work(long)`? **No.** `double -> long` is narrowing.
4. A method declares `save(Number)`. Can you look it up with `Integer.class`? **No.** You must look up `Number.class`; afterwards you can invoke with `Integer`.
5. A method declares `String... names`. What is the type for lookup? **`String[].class`**.
6. Can you use `invoke(receiver, "A", "B")` to automatically pack them into `String[]` for a varargs target method? **No.** A single array argument is required.
7. If the target method throws `IllegalStateException`, through what exception does `invoke` report it? **`InvocationTargetException`**; inspect `getCause()`.
8. If the target method returns `int`, what is the return type of `Method.invoke`? **`Object`**, containing a boxed `Integer`. If the target method returns `void`, `invoke` returns `null`.

## 6. References

- [Oracle Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): documentation for `getMethod`, `getDeclaredMethod`, parameter types, scope, and lookup rules.
- [Oracle Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): documentation for `invoke`, argument convertibility, varargs, return boxing, and exceptions.
- [Java Language Specification SE 21 — §5.1 Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html): widening/narrowing primitive, boxing/unboxing, and conversion contexts.
- [Java Language Specification SE 21 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): overload selection mechanism in **normal Java calls**, helping distinguish it from Reflection lookup.

**Takeaway:** `Class.getMethod/getDeclaredMethod` searches for **a declaration matching the name and parameter types**, while `Method.invoke` checks and **converts the actual arguments** within the limits allowed by the API. Mixing the two phases leads to `NoSuchMethodException`, `IllegalArgumentException`, or selecting the wrong overload.