# 3.7 Passing primitive parameters, boxing, unboxing, widening, and `null` values

**Context:** Java Advance → dynamic-runtime → 3. Reflection.

Reflection allows finding and invoking methods and constructors while the program is running. Difficulties often arise when the target parameter is `int`, `long`, or another primitive type, whereas `Method.invoke(...)` and `Constructor.newInstance(...)` receive arguments via `Object...`. It is necessary to distinguish **the declared parameter type**, **the actual object passed in**, **the valid conversions**, and **the time of error checking**. This lesson fully explains boxing, unboxing, widening, and `null` at the reflection invocation boundary.

## 1. Two distinct phases: finding the right member and invoking that member

**Phase A — signature lookup:** `Class.getMethod(name, parameterTypes...)` and `Class.getConstructor(parameterTypes...)` use `Class<?>` objects to describe the **exact** declared parameter types. Lookup **does not automatically apply** boxing, unboxing, or widening to find a similar overload.

```java
Method m = Service.class.getMethod("update", long.class);
```

The line above looks up the method `update(long)`; `update(int)` or `update(Long)` are different signatures and cannot substitute for it. `getMethod` finds a `public` method accessible via reflection; `getDeclaredMethod` finds a member declared directly on the class, though invocation is still subject to access checks.

**Phase B — invoking the found member:** after obtaining a `Method` or `Constructor`, the JVM checks the number and types of the passed values. At this point, appropriate **unboxing and primitive widening**, or **reference widening**, can occur. For example: `Integer(8)` can be unboxed to `int`, then widened to `long` for the found method `update(long)`.

```text
Class.getMethod("update", long.class)
     │      find EXACT signature
     ▼
Method representing update(long)
     │
Method.invoke(target, 8)
     │      Java boxes 8 into Integer in Object...
     ▼
Reflection: Integer -> int (unboxing) -> long (widening)
     │
     ▼
Execute update(long)
```

`invoke` never automatically searches for the best matching overload based on the runtime object: the overload was already selected when `getMethod` or `getConstructor` was executed.

## 2. Primitives, wrappers, and boxing/unboxing at the reflection boundary

Java has 8 primitive types and 8 corresponding wrappers:

| Primitive | Wrapper | Example argument in `Object[]` |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 3)` |
| `short` | `Short` | `Short.valueOf((short) 3)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(3)` |
| `long` | `Long` | `Long.valueOf(3L)` |
| `float` | `Float` | `Float.valueOf(3.0f)` |
| `double` | `Double` | `Double.valueOf(3.0)` |

**Boxing** converts a primitive value into a wrapper, e.g., `int` → `Integer`. **Unboxing** extracts a primitive from a wrapper, e.g., `Integer` → `int`. In the expression `method.invoke(null, 7)`, the call to `Method.invoke(Object, Object...)` is processed by the **Java compiler** first: `7` of type `int` is boxed into `Integer` to sit inside `Object[]`. When executing a target method with a `long` parameter, **reflection** unboxes `Integer` to `int` and then widens it to `long`.

This does not mean the `Integer` wrapper was converted directly into a `Long` wrapper. If the parameter is **declared as `Long`**, passing an `Integer` is still invalid. Distinguish:

- `long` parameter (primitive): `Integer(7)` is valid because `Integer → int → long`.
- `Long` parameter (reference): `Integer(7)` is **not** converted to `Long(7)`; a `Long` or `null` must be passed.
- `Number` parameter (reference): `Integer(7)` is valid via **reference widening** (`Integer` is a subclass of `Number`).
- `Object` parameter (reference): the wrapper is accepted as an object, with no unboxing required.

`Method.invoke` returns `Object`: if the target method returns `int`, `double`, or another primitive, the return value is **boxed** into the corresponding wrapper; if the target returns `void`, the value from `invoke` is `null`. Returning a primitive array, such as `int[]`, remains an `int[]` array object rather than automatically converting each element into `Integer`.

## 3. Primitive widening: when is it valid?

**Widening primitive conversion** allows converting between primitive types in the following directions, **without automatically inferring the reverse direction**:

| From primitive | Can widen to |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider primitive type |
| `boolean` | Compatible only with `boolean`; does not convert to numbers |

When passing a wrapper for a primitive formal parameter, reflection can **unbox first and widen afterward**. For example:

| Target parameter | Passed object | Result | Why |
| --- | --- | --- | --- |
| `long` | `Byte(7)` | Valid | `Byte → byte → long` |
| `long` | `Integer(8)` | Valid | `Integer → int → long` |
| `double` | `Character('A')` | Valid | `Character → char → double`, value `65.0` |
| `float` | `Long(9L)` | Valid | `Long → long → float` |
| `short` | `Integer(7)` | Error | `int → short` is **narrowing** |
| `int` | `Long(7L)` | Error | `long → int` is **narrowing** |
| `char` | `Byte(65)` | Error | No widening from `byte` to `char` |
| `boolean` | `Integer(1)` | Error | No numeric → boolean conversion |
| `Long` | `Integer(7)` | Error | Two different wrapper types; no automatic unbox–widen–rebox |
| `Number` | `Integer(7)` | Valid | Reference inheritance relationship |

**Implicit narrowing is not allowed** even if the value is small and "fits" the target type. For example, `Integer.valueOf(7)` still cannot be passed to a `short` parameter. If a `short` is intentionally wanted, the caller must check the numeric range and create the exact `Short` (e.g., `Short.valueOf((short) 7)`). `Method.invoke` also does not automatically parse `"7"` into a number, nor does it automatically convert `BigDecimal` to `double`.

A potentially misleading name: **widening does not always mean absolute precision**. Converting `long` to `float` or `double` can round a very large integer due to floating-point representation precision limits, even though that conversion is type-valid.

## 4. `null`: depends on parameter type and how `Object...` is called

`null` cannot be unboxed into a primitive. The following cases must be distinguished:

| Situation | Result |
| --- | --- |
| `String`, `Long`, `Integer`, `Object`... parameter receives `null` | Valid for parameter conversion; target code decides how to handle it |
| `int`, `long`, `boolean`... parameter receives `null` via reflection | `IllegalArgumentException` when argument conversion for the primitive fails |
| Target code receives `Integer == null` and **itself** unboxes it | May throw `NullPointerException` **inside the target method**, wrapped by `Method.invoke` in `InvocationTargetException` |
| Calling an instance method with receiver `obj == null` | `NullPointerException` due to invalid receiver; different from `null` in the parameter list |
| Calling a static method with receiver `obj == null` | Valid: the receiver parameter is ignored for static methods |

### Warning: `null` can be a single argument or the argument array itself

The API signature is `Method.invoke(Object obj, Object... args)`. `Object...` is **varargs at the `invoke` call site**, so how Java constructs the argument array matters greatly:

```java
Method m = Demo.class.getMethod("accept", String.class);

// A single argument with value null:
m.invoke(null, (Object) null);        // passes [null]

// Object[] array representing a single null argument:
m.invoke(null, new Object[]{null});   // passes [null]

// Not a single null argument:
// m.invoke(null, (Object[]) null);   // empty argument list -> wrong argument count
```

The snippet above **illustrates** a static method `Demo.accept(String)` defined elsewhere, so it is not a standalone program. Casting `(Object) null` is very useful to avoid ambiguity in Java's varargs syntax. For a method with **no parameters**, `m.invoke(null, (Object[]) null)` is permitted by the API as an empty argument list.

Do not confuse `null` for the **first argument** (receiver) with `null` inside `args`. For example, `m.invoke(null, (Object) null)` means the static method's receiver is `null` and the target method is passed **one `null` argument**.

## 5. Standalone runnable Java 17+ example verifying each case

Create a file `ReflectionConversionsDemo.java` with the full content below. The two classes `Target` and `Box` are `public static` nested classes so that `public` constructors/methods can be accessed via reflection without needing to bypass access checks.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionConversionsDemo {
    public static class Target {
        public static String longValue(long value) { return "long:" + value; }
        public static String doubleValue(double value) { return "double:" + value; }
        public static String shortValue(short value) { return "short:" + value; }
        public static String longWrapper(Long value) { return "Long:" + value; }
        public static String numberValue(Number value) {
            return "Number:" + (value == null ? "null" : value.getClass().getSimpleName() + ":" + value);
        }
        public static String stringValue(String value) { return "String:" + value; }
        public static int triple(int value) { return value * 3; }
        public static String choose(int value) { return "int overload"; }
        public static String choose(long value) { return "long overload"; }
        public static String join(String... values) {
            return values == null ? "varargs:null" : "varargs:" + values.length;
        }
        public static void fail(int value) { throw new IllegalStateException("boom"); }
    }

    public static class Box {
        private final long value;
        public Box(long value) { this.value = value; }
        @Override public String toString() { return "Box:" + value; }
    }

    private static void attempt(String label, Method method, Object... args)
            throws IllegalAccessException {
        try {
            System.out.println(label + " -> " + method.invoke(null, args));
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> IllegalArgumentException");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> InvocationTargetException("
                    + ex.getCause().getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Target> c = Target.class;
        Method forLong = c.getMethod("longValue", long.class);
        Method forDouble = c.getMethod("doubleValue", double.class);
        Method forShort = c.getMethod("shortValue", short.class);
        Method forWrapper = c.getMethod("longWrapper", Long.class);
        Method forNumber = c.getMethod("numberValue", Number.class);
        Method forString = c.getMethod("stringValue", String.class);
        Method triple = c.getMethod("triple", int.class);
        Method chooseLong = c.getMethod("choose", long.class);
        Method join = c.getMethod("join", String[].class);
        Method fail = c.getMethod("fail", int.class);

        attempt("Byte to long", forLong, Byte.valueOf((byte) 7));
        attempt("Integer to long", forLong, Integer.valueOf(8));
        attempt("Character to double", forDouble, Character.valueOf('A'));
        attempt("Integer to short", forShort, Integer.valueOf(7));
        attempt("Long to int", triple, Long.valueOf(9L));
        attempt("Integer to Long", forWrapper, Integer.valueOf(7));
        attempt("Long to Long", forWrapper, Long.valueOf(7));
        attempt("Integer to Number", forNumber, Integer.valueOf(7));
        attempt("null to String", forString, (Object) null);
        attempt("null to long", forLong, (Object) null);
        attempt("null to Long", forWrapper, (Object) null);

        Object result = triple.invoke(null, 4);
        System.out.println("return boxed -> " + result.getClass().getSimpleName() + ":" + result);

        attempt("choose(long) with Integer", chooseLong, Integer.valueOf(3));
        try {
            c.getMethod("longValue", Integer.class);
            System.out.println("lookup -> FOUND");
        } catch (NoSuchMethodException ex) {
            System.out.println("lookup(Integer.class) -> NoSuchMethodException");
        }

        attempt("String to String...", join, "x");
        attempt("String[] to String...", join, (Object) new String[]{"a", "b"});

        Constructor<Box> constructor = Box.class.getConstructor(long.class);
        System.out.println("constructor Short to long -> "
                + constructor.newInstance(Short.valueOf((short) 5)));

        attempt("target throws", fail, Integer.valueOf(1));
    }
}
```

From the directory containing the file above, compile with Java 17 language level and run:

```bash
javac --release 17 ReflectionConversionsDemo.java
java ReflectionConversionsDemo
```

**Exact stdout** of the program:

```text
Byte to long -> long:7
Integer to long -> long:8
Character to double -> double:65.0
Integer to short -> IllegalArgumentException
Long to int -> IllegalArgumentException
Integer to Long -> IllegalArgumentException
Long to Long -> Long:7
Integer to Number -> Number:Integer:7
null to String -> String:null
null to long -> IllegalArgumentException
null to Long -> Long:null
return boxed -> Integer:12
choose(long) with Integer -> long overload
lookup(Integer.class) -> NoSuchMethodException
String to String... -> IllegalArgumentException
String[] to String... -> varargs:2
constructor Short to long -> Box:5
target throws -> InvocationTargetException(IllegalStateException)
```

Notable points from the output:

1. `Byte → byte → long`, `Integer → int → long`, and `Character → char → double` are **valid**, confirming the ability to unbox then widen.
2. `Integer → short` and `Long → int` are **not** valid because they require narrowing; execution enters the `IllegalArgumentException` branch **before entering the method body**.
3. `Integer` does not automatically convert to `Long`, whereas `Long` into a `Long` parameter works, and `Integer` into a `Number` parameter works due to inheritance.
4. `null` is accepted for reference parameters (`String` and `Long`), and rejected for primitive `long`.
5. `triple(int)` returns `int`, but `Method.invoke` receives the result as an `Integer` object.
6. `choose(long)` was selected via `getMethod("choose", long.class)`. The `Integer` argument is only converted to **invoke the selected overload**; it does not make reflection switch to `choose(int)`.
7. `getMethod("longValue", Integer.class)` does not find `longValue(long)` and throws `NoSuchMethodException`. This is a **lookup error**, distinct from `IllegalArgumentException` during invocation.
8. The `join(String...)` case shows that **varargs on the target method does not cause `Method.invoke` to automatically pack individual arguments**.
9. `Constructor<Box>.newInstance(Short)` uses the same `Short → short → long` rule.
10. When `Target.fail` itself throws `IllegalStateException`, reflection wraps that error in `InvocationTargetException`; the program calls `getCause()` to report the underlying cause.

## 6. Varargs of the target method is not the same as varargs of `Method.invoke`

Suppose a method is declared as follows:

```java
public static String join(String... values) {
    return values == null ? "varargs:null" : "varargs:" + values.length;
}
```

At the bytecode/Reflection level, this last parameter has type **`String[]`**. `getMethod("join", String[].class)` is the correct lookup. `Method.isVarArgs()` helps identify metadata declaring `...`, but a reflection call **does not perform automatic packing like `join("a", "b")` in direct Java call syntax**.

- `joinMethod.invoke(null, "x")`: passes only a single `String` to the `String[]` formal parameter → `IllegalArgumentException`.
- `joinMethod.invoke(null, (Object) new String[]{"a", "b"})`: passes **one** `String[]` object → valid, target sees two elements.
- `joinMethod.invoke(null, (Object) null)`: passes **one** `null` argument for the array parameter (reference type) → target receives `values == null`.
- `joinMethod.invoke(null, new Object[]{new String[]{"a", "b"}})`: also a list containing **one** array argument.
- `joinMethod.invoke(null, new String[]{"a", "b"})`: easily triggers a compiler varargs warning; the `String[]` array may be interpreted as the `Object[]` array of `invoke` itself, resulting in **two** arguments instead of one. Cast to `(Object)` when you want to pass the entire array as a single argument.

The core point: there are **two layers of `...`**; the first layer is Java's compile-time syntax for calling `Method.invoke`, and the second layer is the array type of the parameter declared by the target method. You must control the first layer before reasoning about the second.

## 7. `Constructor.newInstance` applies the same principles

`Constructor<?>.newInstance(Object... initargs)` also takes `Object...` and performs the necessary conversions for constructor parameters.

```java
// Illustration when Box is a public class with constructor public Box(long):
Constructor<Box> ctor = Box.class.getConstructor(long.class);
Box box = ctor.newInstance(Short.valueOf((short) 5));
```

The snippet above uses `Box` from the complete program in section 5. Lookup requires exact `long.class`, while invocation accepts `Short` because of unboxing+widening. Conversely:

- `Box.class.getConstructor(Short.class)`: `NoSuchMethodException` if the class only has `Box(long)`.
- `ctor.newInstance(Integer.valueOf(5))`: valid, `int → long`.
- `ctor.newInstance(Long.valueOf(5))`: valid, `long → long`.
- `ctor.newInstance((Object) null)`: `IllegalArgumentException` because `long` does not accept `null`.
- `ctor.newInstance(Double.valueOf(5))`: `IllegalArgumentException` because `double → long` is narrowing.
- If the **constructor body** throws an exception, `newInstance` wraps the cause in `InvocationTargetException`.

A note on terminology: **reflection does not perform "constructor overload resolution" for you**. Whichever `Constructor` you have, value conversions are applied to invoke **that exact** constructor.

## 8. Distinguishing exceptions for accurate diagnosis

| Exception | Where does it occur? | How to handle |
| --- | --- | --- |
| `NoSuchMethodException` | `getMethod`/`getDeclaredMethod` or `getConstructor` when the signature does not match | Check exact name, exact `.class` of each parameter, `public`/declared, overload |
| `IllegalArgumentException` | `invoke`/`newInstance` when argument count or types are wrong; null for primitive; invalid narrowing; wrong receiver type | Compare `getParameterTypes()` with the runtime class of each argument; do not auto-convert types without rules |
| `InvocationTargetException` | The method/constructor body **already ran** and threw an exception | Check `getCause()` to get the actual error, including `NullPointerException` or `IllegalArgumentException` thrown by target code |
| `NullPointerException` | `null` receiver of an instance method, or unboxing `null` done by Java code itself | Distinguish receiver, arguments, and unboxing in caller/callee code |
| `IllegalAccessException` | Member is not accessible under current permissions | Check visibility and module permissions; this error is independent of value conversion |

Do not catch every exception and turn it into a generic "reflection failed" error, as that loses track of which phase failed. For example, an **`IllegalArgumentException` thrown by the method body** will be inside `InvocationTargetException.getCause()`, distinct from an `IllegalArgumentException` from argument checking **before** invoking the method body.

## 9. How to build safe reflection calls

When receiving values from configuration, JSON, command line, or UI and invoking a method dynamically, clarify the contract first:

1. **Choose the target signature:** obtain `Method`/`Constructor` based on `getParameterTypes()`; for example, `long.class` differs from `Long.class`. If overloads exist, choose deliberately.
2. **Define types and nullability:** is `null` accepted? Are primitives required? If data is missing, explicitly decide whether to report an error or use a default.
3. **Convert at the data boundary:** if the source is a `String` or the wrong numeric type, parse/validate in application logic. Reflection only supports specific conversions, not general-purpose data conversion.
4. **Check narrowing:** if `long` → `int` or `int` → `short` is needed, check the value range and clarify data semantics. Avoid automatic casts that lose information.
5. **Pack the argument array properly:** pass an `Object[]` containing exactly one element per formal parameter; pay attention to array and varargs parameters, especially when an element is `null`.
6. **Categorize errors:** lookup (`NoSuchMethodException`), mismatch (`IllegalArgumentException`), exception from method body (`InvocationTargetException`), and access permissions (`IllegalAccessException`) have different handling paths.

The following **parameter inspection snippet** is an *illustrative snippet* to place in a program that already has a `Method m` object, not a standalone runnable program:

```java
System.out.println("declaringClass = " + m.getDeclaringClass().getName());
System.out.println("name = " + m.getName());
System.out.println("varArgs = " + m.isVarArgs());
for (Class<?> type : m.getParameterTypes()) {
    System.out.println("parameter = " + type.getTypeName());
}
```

When errors involve class loaders, two classes can have the same name without having the same runtime type identity; in that case, `type.getClassLoader()` also needs to be checked. This is an additional step in plugin systems, though it does not change the boxing/unboxing/widening rules explained in this lesson.

## 10. Self-check exercises with answers

**Question 1.** A method has signature `f(double)`. Can `Integer.valueOf(9)` be passed to `Method.invoke`?

**Answer:** Yes. `Integer → int` via unboxing, then `int → double` via widening. The resulting parameter value at the target is `9.0`.

**Question 2.** A method has signature `f(Double)`. Can `Integer.valueOf(9)` be passed?

**Answer:** No. `Integer` is not `Double`; reflection does not automatically perform `Integer → int → double → Double`. If the application wants to convert, create `Double.valueOf(9.0)` before invoking.

**Question 3.** A method has signature `f(short)`. Can `Integer.valueOf(1)` be passed, even though the value is within the `short` range?

**Answer:** No. `int → short` is narrowing and is not applied automatically during invoke. The caller must check and deliberately convert to `Short`.

**Question 4.** What is the difference between `getMethod("f", long.class)` and `invoke(target, Integer.valueOf(1))`?

**Answer:** `getMethod` selects the **exact** overload with a `long` parameter; `invoke` only converts `Integer → int → long` to call that overload. It does not re-lookup the `f(int)` overload.

**Question 5.** Why can `m.invoke(null, (Object) null)` be valid for `f(String)` yet fail for `f(int)`?

**Answer:** Both receive **one** `null` argument. `String` is a reference type and accepts `null`; `int` is a primitive and cannot unbox `null`, resulting in `IllegalArgumentException`.

**Question 6.** Target code `f(Integer value)` executes `int x = value;` when `value` is `null`, and is invoked via reflection. What exception does the caller receive?

**Answer:** The method body causes a `NullPointerException` during unboxing. `Method.invoke` wraps it in `InvocationTargetException`; inspect `getCause()` to obtain the `NullPointerException`.

**Question 7.** For `f(String... values)`, how do you pass two strings as **one array parameter** via reflection?

**Answer:** Look up `getMethod("f", String[].class)`, then call `m.invoke(target, (Object) new String[]{"a", "b"})` or pass `new Object[]{new String[]{"a", "b"}}`. Do not spread the strings as multiple arguments to `invoke`.

**Question 8.** If the target method returns `void` or `int`, what does `Method.invoke` return?

**Answer:** For `void`, it returns `null`; for `int`, it returns an `Integer` containing the return value.

## Summary of rules to remember

- **Lookup by exact signature:** `long.class`, `Long.class`, and `int.class` are distinct parameters.
- **Arguments go through `Object...`:** primitives at the `invoke` call site are usually already boxed by Java into wrappers; reflection can unbox and widen for a primitive formal parameter.
- **Widening is allowed, narrowing is not automatic:** `Integer → long` works; `Long → int` does not, even if the data happens to fit in `int`.
- **One wrapper does not auto-convert to another wrapper:** `Integer` does not automatically become `Long`; reference widening such as `Integer → Number` remains valid.
- **`null` can only be bound to reference types:** for primitives, reflection reports `IllegalArgumentException`; if the method body unboxes `null` itself, that is an exception from target code.
- **Varargs has two layers:** `Method.invoke(Object, Object...)` does not automatically pack varargs of the target method; pass the array properly and cast to `(Object)` when needed.
- **Errors reflect the phase:** `NoSuchMethodException` (lookup), `IllegalArgumentException` (binding/conversion), `InvocationTargetException` (method/constructor body).

### Official references

- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [JLS Java SE 17 — `5.1.2 Widening Primitive Conversion, `5.1.7 Boxing, `5.1.8 Unboxing, `5.3 Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html)