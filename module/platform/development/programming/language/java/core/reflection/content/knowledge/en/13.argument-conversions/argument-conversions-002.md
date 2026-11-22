# Unboxing and Primitive Widening When Calling `Method.invoke` or `Constructor.newInstance`

When calling a method or constructor via Java Reflection, the arguments supplied by the application pass through an API that accepts **`Object` or `Object...`**, whereas the original signature may require `int`, `long`, `double`, or other primitive types. Java Reflection has corresponding conversion rules to pass runtime arguments into the target method/constructor's formal parameters:

1. If a formal parameter is primitive, a compatible argument is typically a **wrapper object** such as `Integer`, `Byte`, or `Character`. Reflection can **unbox** the wrapper into a primitive.
2. After unboxing, Reflection can perform **widening primitive conversion** — for example `byte → long` or `int → double`.
3. Reflection **does not perform narrowing primitive conversion** such as `long → int` or `double → long`, even when the actual value appears to fit in the target range.
4. When the argument count, receiver, access permission, or data type is incompatible, Reflection throws the appropriate exception; in particular, invalid argument conversion typically causes `IllegalArgumentException` **before the target method/constructor body is executed**.

Two central APIs:

~~~java
Object result = method.invoke(receiver, arg1, arg2);
Object created = constructor.newInstance(arg1, arg2);
~~~

These are illustrative expressions: `method` must be `java.lang.reflect.Method`, `constructor` must be `java.lang.reflect.Constructor<?>`; reflection checked exceptions must be handled. This lesson clearly distinguishes **declared formal types**, **argument runtime types**, **unboxing**, **widening**, and common pitfalls when using varargs APIs.

## 1. Context: primitives, wrappers, and APIs accepting `Object...`

Primitives are not objects, but Java has corresponding wrappers:

| Primitive | Wrapper | Object example |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 5)` |
| `short` | `Short` | `Short.valueOf((short) 5)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(5)` |
| `long` | `Long` | `Long.valueOf(5L)` |
| `float` | `Float` | `Float.valueOf(2.5f)` |
| `double` | `Double` | `Double.valueOf(2.5)` |

Source call example:

~~~java
someMethod.invoke(receiver, 5, 2.5);
~~~

At the **call to `invoke(Object, Object...)`**, the expressions `5` and `2.5` are **boxed** by the Java compiler into objects of type `Integer` and `Double` respectively to be placed into the `Object[]` array. Afterwards, when Reflection invokes the **target method**, the wrappers can be **unboxed** and **widened** according to the actual formal signature.

Three layers must be distinguished:

- **Compile time of the Reflection-calling code:** the compiler sees `invoke(Object, Object...)` or `newInstance(Object...)`, rather than automatically selecting an overload of the target method based on each argument.
- **Runtime argument matching:** Reflection checks the number of formal parameters, parameter types, and actual object values, then applies permitted conversions.
- **Invocation of the target body:** only occurs if the required checks and conversions succeed; exceptions inside the body are handled via the `InvocationTargetException` mechanism.

`Constructor.newInstance` is not `Class.newInstance()`. In modern Java, use `getDeclaredConstructor(...).newInstance(...)` or `getConstructor(...).newInstance(...)`; `Class.newInstance()` has been deprecated.

## 2. What is unboxing in Reflection actually?

Suppose the target method is:

~~~java
public static void record(int code) { /* ... */ }
~~~

This is an illustrative method that must be placed inside a Java class. If we look up the `Method` for `record(int)`, the following arguments are compatible:

~~~java
method.invoke(null, Integer.valueOf(7)); // Integer unbox -> int
method.invoke(null, Byte.valueOf((byte) 7)); // Byte unbox -> byte, widen -> int
method.invoke(null, Character.valueOf('A')); // Character unbox -> char, widen -> int
~~~

A `null` receiver is valid here because `record` is a **static method**. For an instance method, the receiver must be an object compatible with the method's declaring type; passing a `null` receiver causes `NullPointerException`.

Key point: Reflection is **not** a general-purpose converter. It does not parse `"7"` into `int`, does not call `Number.intValue()` for arbitrary `Number` subtypes, and does not pick the "closest numeric type" by value.

~~~java
method.invoke(null, "7");      // Wrong type -> IllegalArgumentException
method.invoke(null, null);     // Ambiguous syntax due to varargs; cast explicitly for clarity.
method.invoke(null, (Object) null); // One null argument for int -> IllegalArgumentException
~~~

In a direct call `method.invoke(null, null)`, Java may interpret `null` as **the entire `Object[]` array of varargs** and the compiler issues a warning; therefore use `(Object) null` or `new Object[] { null }` when intentionally passing **a single null argument**. For a target method with a primitive parameter, null cannot be unboxed and Reflection reports `IllegalArgumentException`.

### Wrapper must match the source primitive type

For formal type `int`, `Integer`, `Byte`, `Short`, and `Character` all have valid unbox-then-widen paths. However, `Long` and `Double` have no widening path to `int`:

~~~java
method.invoke(null, Long.valueOf(7L));   // No long -> int widening
method.invoke(null, Double.valueOf(7.0)); // No double -> int widening
~~~

Both are invalid even though the numeric value is 7. To perform intentional "narrowing", the application must explicitly decide on an overflow/precision policy and **convert before calling Reflection**.

## 3. Table of permitted primitive widenings

Java allows **identity** (keeping the same primitive type) and the following *widening primitive conversion* directions:

| Source primitive after unboxing | Permitted target primitives besides itself |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider primitive type |
| `boolean` | No numeric conversion; only compatible with `boolean` |

For example, if the formal parameter is `double`, you can pass `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, or `Double` via the corresponding conversions. If the formal parameter is `char`, then only `Character` among these primitive wrappers matches; `Byte`/`Short` do not widen to `char`.

**Widening does not always mean preserving exact numeric precision.** For instance, `long → float` can lose some representation precision; nevertheless, the widening conversion is permitted by Java. Reflection follows type rules and does not block a widening conversion merely because precision might be lost.

### Only unbox then widen, no "wrapper widening"

`Integer` is **not** a subtype of `Long` and Reflection does not automatically apply `Integer → int → long → Long` to fill a **`Long`** formal parameter:

~~~java
public static void boxed(Long value) { /* ... */ }
~~~

If you pass `Integer.valueOf(5)` to the `Long` formal parameter, the Reflection call is incompatible. The formal parameter is the reference type `Long`, so the fundamental validity rule is reference compatibility; **there is no conversion between two different wrapper classes merely because their corresponding primitives have widening**.

Conversely, if the formal parameter is the reference `Number` or `Object`, then `Integer` can be passed via **widening reference**:

~~~java
public static void accept(Number value) { /* ... */ }
~~~

`Integer` is a subclass of `Number`; no unboxing is needed to call `accept(Number)`. This is why you must always check the **formal parameter type** before concluding whether a conversion applies.

## 4. `Method.invoke`: identifying formal parameters and converting arguments

Example target method:

~~~java
public String describe(int code, double score, boolean enabled) {
    return code + "," + score + "," + enabled;
}
~~~

If it resides in class `Target`, we look up `Method` using the **exact** formal parameter types:

~~~java
Method describe = Target.class.getMethod(
        "describe", int.class, double.class, boolean.class);
~~~

`getMethod`/`getDeclaredMethod` **does not automatically look up methods by wrapper types or select overloads by widening**. For example, `getMethod("describe", Integer.class, Double.class, Boolean.class)` is not the way to find a method with descriptor `(int, double, boolean)`. You must pass the `Class` objects matching the method signature.

Once the `Method` is retrieved, the runtime arguments are unboxed/widened:

~~~java
Object value = describe.invoke(
        target,
        Character.valueOf('A'), // char -> int (character code value 65)
        Integer.valueOf(7),     // int -> double (7.0)
        Boolean.TRUE            // boolean -> boolean
);
~~~

`target` must be an instance of the class declaring `describe` (or a compatible subtype). `Method.invoke` returns `Object`: if the method returns a primitive, Reflection **boxes** the result into a wrapper; if it returns `void`, the result is `null`; if it returns a reference, you receive the resulting object according to the method's semantics.

### What `Method.invoke` does not do automatically

- Does not convert `String` to primitive via parsing.
- Does not perform narrowing such as `double → int` or `long → short`.
- Does not invoke another overload when the current argument is incompatible.
- Does not turn `Integer[]` into `int[]` or convert individual array elements. An `int[]` array parameter must receive an actual array object of a compatible type.
- Does not "fix" erased generic types; if a method accepts `List<Integer>`, the runtime parameter class is still usually `List.class` and verifying element types must be done separately.

## 5. `Constructor.newInstance` uses the same conversion rules

Suppose the constructor is:

~~~java
public Target(long count, double amount) {
    this.count = count;
    this.amount = amount;
}
~~~

With an appropriate `Target` class, look up the constructor by its formal signature:

~~~java
Constructor<Target> ctor =
        Target.class.getConstructor(long.class, double.class);
~~~

When creating the object:

~~~java
Target target = ctor.newInstance(
        Byte.valueOf((byte) 5), // byte -> long
        Float.valueOf(1.25f)    // float -> double
);
~~~

Valid because `Byte` unboxes to `byte` and widens to `long`; `Float` unboxes to `float` and widens to `double`. If the first argument is changed to `Double.valueOf(5.0)`, the formal type is still `long`, so **narrowing `double → long` cannot be used**; `newInstance` throws `IllegalArgumentException` without executing the corresponding constructor body.

How to look up constructors:

- `getConstructor(Class<?>...)` finds a matching **public constructor**.
- `getDeclaredConstructor(Class<?>...)` finds a constructor declared on the class (including private ones); finding metadata does not automatically grant invocation permission. If the constructor is not accessible, `IllegalAccessException` may occur; with named modules, `setAccessible` capability also depends on exports/opens.
- Constructor arguments must match in exact count; `Constructor.newInstance` does not select an overload based on argument values.
- A non-static inner class constructor may have a hidden parameter representing the enclosing class instance; you must understand the real descriptor when using Reflection.

`Constructor.newInstance` returns a new object of the class declaring the constructor. It **does not** return a primitive value, so there is no *return value* boxing step as in `Method.invoke`.

## 6. Complete runnable example (Java 17+)

Create a single file named **`ReflectiveConversionDemo.java`**. The program observes simultaneously:

- Wrapper `Byte` unboxed/widened to constructor formal `long`.
- Wrapper `Float` unboxed/widened to constructor formal `double`.
- Wrapper `Character` unboxed/widened to method formal `int`.
- Wrapper `Integer` unboxed/widened to method formal `double`.
- `Long → int`, `Double → long`, and `null → int` rejected.
- An `int[]` parameter passed as a single `Object`.
- A method returning `int` boxed by Reflection into `Integer`; an exception thrown by the target wrapped in `InvocationTargetException`.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveConversionDemo {
    public static final class Target {
        final long count;
        final double amount;

        public Target(long count, double amount) {
            this.count = count;
            this.amount = amount;
        }

        public String describe(int code, double score, boolean enabled) {
            return count + "," + amount + "," + code + "," + score + "," + enabled;
        }

        public static int sum(int[] values) {
            int total = 0;
            for (int value : values) total += value;
            return total;
        }

        public static void fail(int value) {
            throw new IllegalStateException("inside");
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Target> ctor = Target.class.getConstructor(long.class, double.class);
        Target target = ctor.newInstance(Byte.valueOf((byte) 5), Float.valueOf(1.25f));
        Method describe = Target.class.getMethod(
                "describe", int.class, double.class, boolean.class);

        Object result = describe.invoke(
                target, Character.valueOf('A'), Integer.valueOf(7), Boolean.TRUE);
        System.out.println("invoke: " + result);

        Method sum = Target.class.getMethod("sum", int[].class);
        Object answer = sum.invoke(null, (Object) new int[] {1, 2, 3});
        System.out.println("primitive return: " + answer + " (" + answer.getClass().getSimpleName() + ")");

        try {
            describe.invoke(target, Long.valueOf(65L), Integer.valueOf(7), Boolean.TRUE);
        } catch (IllegalArgumentException e) {
            System.out.println("Long to int: " + e.getClass().getSimpleName());
        }

        try {
            describe.invoke(target, null, Integer.valueOf(7), Boolean.TRUE);
        } catch (IllegalArgumentException e) {
            System.out.println("null to int: " + e.getClass().getSimpleName());
        }

        try {
            ctor.newInstance(Double.valueOf(5.0), Float.valueOf(1.25f));
        } catch (IllegalArgumentException e) {
            System.out.println("Double to long: " + e.getClass().getSimpleName());
        }

        try {
            Target.class.getMethod("fail", int.class).invoke(null, Integer.valueOf(9));
        } catch (InvocationTargetException e) {
            System.out.println("target threw: " + e.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Compile/run commands (JDK 17 or later):

~~~bash
javac --release 17 -Xlint:all ReflectiveConversionDemo.java
java ReflectiveConversionDemo
~~~

**Exact stdout** (compiled with `--release 17 -Xlint:all` and executed successfully):

~~~text
invoke: 5,1.25,65,7.0,true
primitive return: 6 (Integer)
Long to int: IllegalArgumentException
null to int: IllegalArgumentException
Double to long: IllegalArgumentException
target threw: IllegalStateException
~~~

Explanation in order:

1. `Byte(5)` goes into constructor `long` and `Float(1.25)` into `double`: both unbox + widen sequences are valid, and the `Target` object is instantiated.
2. `Character('A')` is unboxed to `char` and widened to `int` giving character code value `65`; `Integer(7)` becomes `double 7.0`; `Boolean.TRUE` matches `boolean`.
3. The `sum` method takes **one `int[]`**; the primitive `int` result of value `6` is returned by Reflection via `Object` as an `Integer`.
4. `Long → int`, `null → int`, and `Double → long` do not satisfy valid conversions and are rejected with `IllegalArgumentException`.
5. `fail` receives valid argument `Integer(9)`, executes its body, and throws `IllegalStateException`. **`Method.invoke` itself wraps the target exception** in `InvocationTargetException`; the program prints the type name of `getCause()`.

Do not infer from the `IllegalArgumentException` lines that the target method body ran: those are **argument matching/conversion** errors. By contrast, the `target threw` line proves the body ran and threw an exception.

## 7. Designing a data conversion layer before calling Reflection

In frameworks or programs that load methods from configuration, input data is often a `String`, JSON value, or general numeric type. If you need to convert `"42"` to `int`, or `Long(42)` to `int`, do it in a **separate adaptation/validation layer**, and only then call Reflection:

1. Retrieve formal types via `method.getParameterTypes()` or `constructor.getParameterTypes()`.
2. Check argument count and handle varargs according to the real descriptor; convert data with explicit policies.
3. For narrowing, check range, rounding, and precision loss before creating the target wrapper; for example `Math.toIntExact(long)` can reject values outside the `int` range.
4. Pass compatible objects/wrappers or arrays into `invoke` / `newInstance`; handle `IllegalArgumentException` for mismatches and `InvocationTargetException` for errors thrown by the target.
5. Ensure access to the right constructor/method and respect module access, without opening private internals unnecessarily.

Example **application conversion snippet**, not part of automatic Reflection:

~~~java
long input = 42L;
int checked = Math.toIntExact(input); // Explicitly accepts values within the int range.
method.invoke(receiver, Integer.valueOf(checked)); // For a method accepting int.
~~~

For numeric domains requiring high precision or financial data, `double` and float widening type rules are insufficient to guarantee desired arithmetic; choose an appropriate data/validation model (such as `BigDecimal` when exact decimal representation is required).

## References

- [Java SE 21 — `java.lang.reflect.Method.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)).
- [Java SE 21 — `java.lang.reflect.Constructor.newInstance`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
- [Java Language Specification §5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2), [§5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [§5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3).