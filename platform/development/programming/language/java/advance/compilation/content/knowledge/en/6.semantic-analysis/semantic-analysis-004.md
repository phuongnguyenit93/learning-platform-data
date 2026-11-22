# Type Conversions, Boxing, Unboxing, and Runtime-Only Errors

In Java, the compiler `javac` inspects the **static type** of expressions to decide whether an assignment, method invocation, or cast is *permitted*. When permitted, Java may perform implicit or explicit type conversions. Some conversions preserve values; some can lose precision; some must check the actual object at runtime; and **unboxing a `null` reference can throw `NullPointerException`**.

Therefore, "`javac` compiled successfully" does not mean "every input value can be converted at runtime." This lesson belongs to the **Semantic Checking** section: understanding conversion contexts and boxing/unboxing to explain the boundary between compile-time errors, converted values differing from expectations, and runtime exceptions. Examples use Java 17+.

## 1. The big picture: static types, runtime values, and conversions

Distinguish three steps:

1. **Static type**: the compiler knows what declared type an expression has (`int`, `Integer`, `Object`, `Number`, ...), and relies on Java rules to permit or reject a conversion.
2. **Conversion**: in an appropriate context, Java can convert from primitive to primitive, primitive to wrapper, wrapper to primitive, or reference type to reference type.
3. **Value at runtime**: an `Object` variable might point to a `String`, an `Integer`, or `null`. Reference conversions requiring a runtime check succeed only if the actual object is compatible; unboxing succeeds only when the reference is not `null`.

~~~text
Java source (.java)
       │
       ▼
javac: check static types, conversion rules, overloads, generics
       │
       ├── No valid conversion ──────────► compile-time error
       │
       ▼
class file (.class)
       │
       ▼
JVM: execute operations and required runtime conversions
       │
       ├── Compatible value ─────────────► result
       ├── null is unboxed ──────────────► NullPointerException
       └── wrong-type reference cast ────► ClassCastException
~~~

In the JLS, the main conversion categories include **identity, widening/narrowing primitive, widening/narrowing reference, boxing, unboxing, unchecked, capture, and string conversion**. Not every category applies in every context. Assignments, method invocations, casts, and numeric operators have different sets of allowed conversions.

## 2. Conversions between primitive types

### 2.1. Widening primitive: expanding the representation range

Common example:

~~~java
int count = 42;
long total = count;      // int -> long, implicit
double measure = total;  // long -> double, implicit
~~~

Conversions such as `byte → short → int → long`, `int → double`, or `float → double` normally require no cast. However, **widening does not always preserve numerical precision**: converting a very large `long` to `float` or `double` can involve rounding due to significant-digit limits. "Widening" describes permitted type rules, not a promise that values remain intact in every case.

Every assignment must also obey the conversion table: `boolean` does not participate in numeric conversions; `char` is a 16-bit unsigned integer type in numeric conversion contexts, yet `char` cannot automatically receive from `short`.

### 2.2. Narrowing primitive: casting that can lose information

An `int` value can exceed the `byte` range (-128 to 127), so converting in the narrowing direction usually requires an explicit cast:

~~~java
int value = 130;
byte narrowed = (byte) value;
System.out.println(narrowed); // -126
~~~

`(byte) 130` takes the representation fitting the 8-bit width, so the result is `-126`. The cast is valid and **throws no exception** when value bits are lost. This is an important example: not every "dangerous" conversion fails at runtime; some conversions succeed and produce a different value than intended.

A useful exception in an **assignment context**: a constant expression of type `int` within the representable range can be assigned directly to `byte`/`short`/`char` and, in certain cases, the corresponding wrappers.

~~~java
byte small = 100;       // Valid: int constant expression fits byte range
char letter = 65;       // Valid: int constant expression fits char range
// byte tooBig = 128;   // Compile error: does not fit byte range

int dynamic = 100;
// byte b = dynamic;     // Compile error: dynamic is not a constant expression
byte b = (byte) dynamic; // Valid thanks to cast
~~~

**Do not generalize this constant rule to all contexts.** For example, `void accept(byte b)` cannot be called with `accept(100)` merely because `100` fits in the byte range: method invocation contexts do not have the same constant `int` narrowing conversion as assignment contexts.

### 2.3. Converting from floating-point to integral

Casting from `double`/`float` to `int`/`long` does not simply "throw an exception if out of range":

- Fractional parts are truncated toward 0 when the result fits in the representable range.
- For finite values that are too large or too small, conversion to the corresponding wide integral target clamps to the endpoint and may then narrow to the target type.
- `NaN` converts to 0 for integer types.
- There is no `ArithmeticException` merely because this explicit cast loses data.

~~~java
public class NumericConversionDemo {
    public static void main(String[] args) {
        System.out.println((int) 3.9);
        System.out.println((int) -3.9);
        System.out.println((int) Double.NaN);
        System.out.println((int) Double.POSITIVE_INFINITY);
        System.out.println((byte) 130);
    }
}
~~~

Run:

~~~bash
javac --release 17 NumericConversionDemo.java
java NumericConversionDemo
~~~

Exact stdout:

~~~text
3
-3
0
2147483647
-126
~~~

Note that some conversions in the JLS have two steps, such as `double` to `byte`: from floating to `int` and then from `int` to `byte`. Do not replace specific rules with a guess like "the JVM always truncates bits."

## 3. Numeric promotion and arithmetic operators

When using `+`, `-`, `*`, `/`, numeric comparison operators, and many other operators, Java applies appropriate **numeric promotion** to bring operands to the type used for the operation.

A common case: `byte`, `short`, and `char` are promoted to `int` in ordinary binary operations.

~~~java
byte a = 10;
byte b = 20;
// byte sum = a + b;     // Error: a + b has type int
int sum = a + b;         // Valid
byte narrowSum = (byte) (a + b);
~~~

Having `byte` variables does not mean every operation on them also returns `byte`. Similarly, `char + 1` is an integer expression; if you want to assign back to `char`, you must choose an appropriate conversion.

With compound assignment, Java has an implicit conversion:

~~~java
byte n = 127;
n += 1;                   // Equivalent in value: n = (byte) (n + 1)
System.out.println(n);    // -128
~~~

`n = n + 1` is invalid because the right-hand expression has type `int`. Meanwhile `n += 1` is valid, yet **it can still overflow/narrow the value**. Compound assignment operators are not exempt from numeric rules.

For 32/64-bit integer types, addition/subtraction/multiplication beyond the representable range normally **throws no exception** and wraps around according to Java's representation; if you want to detect overflow, use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, or appropriate range checks. Integer division by 0 is a different runtime error example: `ArithmeticException`.

## 4. Boxing: primitive to wrapper

The eight common pairs are:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

**Boxing** is the conversion from a primitive value to a reference of the corresponding wrapper. For example:

~~~java
int primitive = 42;
Integer boxed = primitive;      // Autoboxing
Integer explicit = Integer.valueOf(primitive);
Object asObject = primitive;    // Boxing int -> Integer, then reference widening -> Object
~~~

Autoboxing in source code has a value effect equivalent to obtaining a wrapper for the primitive, typically lowered by the compiler to calls like `Integer.valueOf(...)`. However, do not infer that every boxing operation necessarily allocates a new object: wrappers may cache instances. Furthermore, boxing can consume memory resources, though the common conversion-related mistake learners encounter is **unboxing null**, not boxing itself.

**There is no automatic "widen primitive then box" chain in normal assignment**:

~~~java
Integer good = 10;      // int -> Integer
Long alsoGood = 10L;    // long -> Long
// Long bad = 10;       // Compile-time error: no automatic int -> long -> Long
~~~

If you need `Long`, use the literal `10L`, or convert/construct with an explicit type (e.g., `Long.valueOf(10L)`).

Boxing also occurs when calling APIs taking objects or putting primitives into generic collections:

~~~java
import java.util.ArrayList;
import java.util.List;

class BoxingWithList {
    static List<Integer> values() {
        List<Integer> result = new ArrayList<>();
        result.add(7); // int -> Integer
        return result;
    }
}
~~~

The generic type argument `Integer` is a reference type; you cannot write `List<int>` in Java 17. Java Collections store references to wrappers, and boxing/unboxing can occur when retrieving and computing data.

## 5. Unboxing: wrapper to primitive

**Unboxing** extracts the primitive value from a wrapper:

~~~java
Integer boxed = 21;
int unboxed = boxed;            // Integer -> int
int explicit = boxed.intValue();
long promoted = boxed;          // Integer -> int -> long
~~~

Unboxing can happen without source code writing `intValue()`, for example in assignments, arithmetic operations, and some method invocations.

~~~java
Integer left = 20;
Integer right = 22;
int sum = left + right;         // Two unboxings, then int addition
~~~

A crucial difference: **wrappers are references and can be `null`**, whereas primitives `int`, `long`, `boolean`, etc., cannot hold `null`.

~~~java
Integer maybe = null;
// int n = maybe;         // Compiles, but running it will throw NullPointerException
~~~

The `//` line is disabled for demonstration only; if enabled and executed, it will throw `NullPointerException` at the moment of unboxing. `javac` permits it because static type `Integer` can be converted to `int`; in general, the compiler does not guarantee a reference is non-`null` across all runtime branches.

### Hidden places where unboxing happens that you need to spot

~~~java
Integer number = null;
Boolean flag = null;

// if (number > 0) { }    // Integer -> int: NPE if number is null
// if (number == 0) { }   // Comparing Integer with int: NPE
// int x = number + 1;    // Arithmetic operator: NPE
// if (flag) { }          // Boolean -> boolean: NPE
// boolean b = !flag;     // Boolean negation: NPE
~~~

Notably, `number == null` only compares the reference to `null`, **needs no unboxing**, and is a safe check. Likewise, string concatenation `"value=" + number` can print `"value=null"` without forcing unboxing, because that is string conversion.

## 6. Hands-on example: code compiles, error occurs only at runtime

File `RuntimeConversionDemo.java`:

~~~java
public class RuntimeConversionDemo {
    static int increment(Integer value) {
        return value + 1; // Unboxing when evaluating addition
    }

    public static void main(String[] args) {
        System.out.println(increment(41));

        try {
            Integer missing = null;
            System.out.println(increment(missing));
        } catch (NullPointerException ex) {
            System.out.println("Caught: NullPointerException");
        }

        Object value = "hello";
        try {
            Integer count = (Integer) value;
            System.out.println(count);
        } catch (ClassCastException ex) {
            System.out.println("Caught: ClassCastException");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 RuntimeConversionDemo.java
java RuntimeConversionDemo
~~~

Exact stdout:

~~~text
42
Caught: NullPointerException
Caught: ClassCastException
~~~

Analysis:

- `increment(41)` is valid: primitive `int` is boxed to `Integer` when calling `increment(Integer)`. When evaluating `value + 1`, the wrapper is unboxed back to `int`.
- `increment(null)` is also valid by **static type** because the parameter is reference `Integer`, but when evaluating `value + 1` with `value == null`, unboxing throws `NullPointerException`.
- `Object value = "hello"` is a widening reference conversion from `String` to `Object`. The cast `(Integer) value` is accepted by the compiler as a plausible cast, yet the JVM checks the actual object: `String` is not an `Integer`, so it throws `ClassCastException`.
- `try/catch` in the example is used solely to observe both exception types and continue printing output. In real systems, prevent errors with input contracts and proper validation rather than using exceptions as routine handling for every conversion.

## 7. Widening and narrowing reference: distinct from primitive conversion

Widening reference conversion goes from a subtype to an appropriate supertype, normally requiring no runtime check:

~~~java
Integer integer = 9;
Number number = integer; // Integer -> Number
Object object = number;   // Number -> Object
~~~

The actual object is still `Integer`. Assigning `Number` to `Object` does not turn the object into a new `Object` instance or change its identity.

Narrowing reference conversion goes in the direction that requires more specific checking:

~~~java
Object value = "Java";
String text = (String) value; // Succeeds at runtime

Object another = Integer.valueOf(10);
// String wrong = (String) another; // Compiles, runtime ClassCastException
~~~

If the compiler proves two types cannot convert for any valid object, it rejects the cast right at compile time. For example, casting directly from `String` to `Integer` is inconvertible types and rejected; through an `Object` variable it can be syntactically and type-wise valid, yet checked at runtime.

`instanceof` helps check the actual type before extracting subtype-dependent information:

~~~java
Object input = "Java 17";
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

The stdout of this snippet if placed in `main` is `7`. Java 17 supports pattern matching for `instanceof`; for `null`, `instanceof String` returns `false`. This is a way to reduce dangerous casts when inputs can have multiple valid types. It does not replace data content validation, nor does it prove all generic type arguments due to erasure.

## 8. Overload resolution: widening differs from boxing

A point directly tied to `javac`'s semantic checks is **compile-time overload selection**. Java tries method applicability phases (strict invocation first, then loose invocation if needed, then variable arity). In simple cases, a call may prefer primitive widening before boxing, even though boxing also looks plausible.

File `OverloadConversionDemo.java`:

~~~java
public class OverloadConversionDemo {
    static void choose(long x) {
        System.out.println("long");
    }

    static void choose(Integer x) {
        System.out.println("Integer");
    }

    static void accept(Number x) {
        System.out.println("Number");
    }

    public static void main(String[] args) {
        choose(10);                // int -> long in strict invocation phase
        choose(Integer.valueOf(10)); // Integer matches directly
        accept(10);                // int -> Integer -> Number
    }
}
~~~

Run:

~~~bash
javac --release 17 OverloadConversionDemo.java
java OverloadConversionDemo
~~~

Exact stdout:

~~~text
long
Integer
Number
~~~

Method selection is not based on a simple rule like "widening always beats boxing" across every overload; the signature list, generics, varargs, subtypes, and call specificity all matter. This process also differs from dynamic dispatch: overloading **selects the signature at compile time**, whereas overriding of instance methods can be dynamically dispatched at runtime.

Do not try to "fix" overloads with arbitrary casts. If an API causes ambiguity or is too hard to predict, naming methods with clear intent or declaring consistent parameters is usually easier to maintain.

## 9. Conditional operator and unexpected NullPointerException

The conditional operator `condition ? a : b` **evaluates only one of the two branches**, yet its result type is determined by the compiler from **the types of both branches**. That can force unboxing the value of the chosen branch.

~~~java
Integer absent = null;
boolean useFallback = true;
int safe = useFallback ? 1 : absent; // Result is 1; absent branch is not evaluated
~~~

If `useFallback` is `false`, the `absent` branch is chosen and unboxed to `int` according to the type rules of numeric conditional expressions, causing an NPE. Do not infer that "one branch is `Integer`, so the whole expression is `Integer`."

Runnable example:

~~~java
public class TernaryUnboxingDemo {
    public static void main(String[] args) {
        Integer missing = null;
        System.out.println(true ? 1 : missing);
        try {
            System.out.println(false ? 1 : missing);
        } catch (NullPointerException ex) {
            System.out.println("ternary: NullPointerException");
        }
    }
}
~~~

~~~bash
javac --release 17 TernaryUnboxingDemo.java
java TernaryUnboxingDemo
~~~

Stdout:

~~~text
1
ternary: NullPointerException
~~~

A common way to handle needing a primitive number with a fallback is an explicit `null` check:

~~~java
Integer input = null;
int result = input == null ? 0 : input;
System.out.println(result); // 0
~~~

If business logic needs to distinguish "no data" from the value `0`, keep a wrapper/`OptionalInt` or an appropriate domain representation instead of conflating the two states.

## 10. Comparing wrappers: value differs from identity

The `==` operator on **two wrapper references** checks whether they are the same object; on **one wrapper and one primitive of the corresponding numeric group**, numeric promotion usually leads to unboxing and comparing primitive values.

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true, equal by value
System.out.println(a == 1000);    // true, unboxed then numeric comparison
~~~

Do not use `a == b` as a value check. Some wrappers have caches and Java specifies reference identity in certain small-value boxing cases; for instance, an identity check on small numbers might appear to work, then fail with larger data or a different environment. You should not design logic based on cache details.

With nullable references:

~~~java
Integer maybe = null;
System.out.println(maybe == null); // true, does not unbox
// System.out.println(maybe == 0); // NPE if uncommented
~~~

You can use `java.util.Objects.equals(a, b)` to compare two wrappers by value safely with `null`. For ordering comparisons (<, >), primitives are a good choice when data must exist; if using nullable wrappers, establish a handling policy before performing operations.

## 11. Generic erasure: casts can be deferred until element read

Java generics support compile-time type checking, but **type erasure** means runtime does not fully verify `List<String>` for every element on all paths. As soon as a raw type or unchecked cast breaks the guarantee, an error can surface **when reading data**.

File `HeapPollutionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List raw = names;
        raw.add(Integer.valueOf(5)); // Raw type bypasses String check at compile time

        try {
            String name = names.get(0); // Compiler-generated cast to String
            System.out.println(name);
        } catch (ClassCastException ex) {
            System.out.println("generic: ClassCastException");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 HeapPollutionDemo.java
java HeapPollutionDemo
~~~

Stdout:

~~~text
generic: ClassCastException
~~~

The compiler inserted an appropriate type check when reading `String name = names.get(0)`; it does not continuously verify at runtime that the list contains only Strings. `@SuppressWarnings` in the example is solely to isolate the behavior; in real code, **do not hide raw/unchecked warnings** unless there is a controlled conversion boundary. Compile-time warnings are signals to address in order to avoid runtime errors far from the cause.

A cast like `(List<String>) obj` also cannot precisely verify each type argument merely through runtime erasure; a generic collection does not automatically "become a clean List<String>" after casting.

## 12. Array covariance: valid at compile time, ArrayStoreException at runtime

Reference-type arrays have **covariance**: `String[]` can be assigned to `Object[]`. Yet the array object still knows its actual runtime component type, so writing an element of the wrong type is blocked.

~~~java
public class ArrayStoreDemo {
    public static void main(String[] args) {
        Object[] items = new String[1];
        try {
            items[0] = Integer.valueOf(7);
        } catch (ArrayStoreException ex) {
            System.out.println("array: ArrayStoreException");
        }
    }
}
~~~

~~~bash
javac --release 17 ArrayStoreDemo.java
java ArrayStoreDemo
~~~

Stdout:

~~~text
array: ArrayStoreException
~~~

The compiler sees `items` has static type `Object[]`, so an `Integer` is a valid `Object` value to assign in source code. The JVM, however, knows the actual array is `String[]` and checks the element on write. This is a **different runtime type-checking error** from `ClassCastException`. Do not infer that generic `List<Number>` also accepts `List<Integer>`: Java's generic type arguments are normally invariant.

## 13. Distinguishing runtime errors from silent value loss

Not every bad result throws an exception, and not every runtime exception comes from casting.

| Scenario | Compile time | At execution time |
| --- | --- | --- |
| `byte b = 128;` | **Error**: constant does not fit byte range | Cannot run |
| `byte b = (byte) 128;` | **Valid** | Value is `-128`, no exception |
| `int n = (int) Double.NaN;` | **Valid** | `n == 0` |
| `Integer n = null; int x = n;` | **Valid** | `NullPointerException` on unbox |
| `Object x = "hi"; Integer n = (Integer) x;` | **Valid** | `ClassCastException` |
| `Object[] a = new String[1]; a[0] = 1;` | **Valid** | `ArrayStoreException` |
| `int x = Integer.MAX_VALUE + 1;` | **Valid** | Result `-2147483648`; no exception |
| `Math.addExact(Integer.MAX_VALUE, 1)` | **Valid** | `ArithmeticException` |
| `Long n = 1;` | **Error**: no implicit int → long → Long | Cannot run |

Combined example — `OverflowDemo.java`:

~~~java
public class OverflowDemo {
    public static void main(String[] args) {
        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println(wrapped);

        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("checked: ArithmeticException");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 OverflowDemo.java
java OverflowDemo
~~~

Stdout:

~~~text
-2147483648
checked: ArithmeticException
~~~

If you need to guarantee no data loss in integer conversions, **check valid ranges before casting**. If overflow during addition or multiplication is a business error, prefer exact arithmetic or a data type with an appropriate range. If external data can be `null`, check for null before unboxing, especially at HTTP/JSON/database boundaries.

## 14. Compile-time errors that javac catches early

The file `InvalidConversions.java` below is **code that intentionally fails to compile**. Do not run it together with the valid examples:

~~~java
class InvalidConversions {
    void demo() {
        int primitive = 5;
        // boolean flag = primitive; // Java does not convert int to boolean

        // Integer n = "5";          // String cannot be assigned to Integer
        // byte b = primitive;        // int variable -> byte requires a cast
        // Long big = 5;              // No implicit int -> long -> Long
        // int fromNull = null;       // No direct conversion from null to primitive

        String s = "ok";
        // Integer impossible = (Integer) s; // Two final class types cannot be cast directly
    }
}
~~~

The erroneous lines are commented out to focus on meaning. If you remove `//` on each corresponding line, `javac` reports a compile-time error. Unlike `Object x = "hi"; Integer n = (Integer) x;`, the compiler immediately sees variable `s` has type `String`, so there is no valid direct narrowing reference conversion to `Integer`.

**Read error messages in context:** the compiler may report `incompatible types`, `possible lossy conversion`, or `inconvertible types`; exact wording and positions can vary across JDK versions. What matters is which conversion rule was violated.

## 15. Looking at bytecode to see conversions happen

You can use `javap` to inspect compiled methods:

~~~bash
javac --release 17 RuntimeConversionDemo.java
javap -c -p RuntimeConversionDemo
~~~

For Java code using boxing/unboxing, bytecode on common `javac` versions can show calls like `Integer.valueOf(int)` and `Integer.intValue()`. Narrowing reference casts usually have a `checkcast` instruction. Primitive arithmetic uses appropriate instructions such as `iadd`.

You do not need to memorize instruction sequences to understand errors; simply grasp:

- **Compile time** determines whether a conversion is valid by static types and can insert conversion operations.
- **Runtime** executes those operations on actual values; `null` or wrong-type references can throw exceptions.
- **Erasure** can lead to extra casts when using generics.
- **Primitive narrowing** can produce unintended values without throwing exceptions.

Exact bytecode shapes can vary between JDKs, so treat `javap` output as verification data for **one specific compilation**, not text guaranteed to remain identical across all versions.

## 16. How to write code that reduces conversion bugs

1. **Prefer primitives** if data always exists and does not need `null`: `int`/`long` avoid unnecessary boxing and unboxing NPEs.
2. **Use wrappers deliberately** when data can be absent or an API requires references; define clear null conventions and validate at boundaries.
3. **Do not use `==` on two wrappers for value comparison**; use `equals`/`Objects.equals`, or unbox safely and compare primitives.
4. **Limit raw types and unchecked casts**: retain generic type information in source code; address warnings instead of suppressing them wholesale.
5. **Check types before narrowing reference casts** when receiving `Object` or polymorphic data (`instanceof`, pattern matching).
6. **Choose controlled numeric conversions**: validate ranges when performing narrowing casts, use `Math.toIntExact(long)` to detect `long` outside `int` range (throws `ArithmeticException`), or `Math.addExact` when overflow must be caught.
7. **Write boundary tests**: `null`, negative numbers, `0`, min/max, wrong-type collection elements, closely related overloads, out-of-range values, and rare conditional branches.

Example of expressing conversion intent clearly:

~~~java
import java.util.Objects;

public class SafeConversions {
    static int required(Integer number) {
        return Objects.requireNonNull(number, "number must not be null");
    }

    static long widen(int value) {
        return value;
    }

    static int checkedNarrow(long value) {
        return Math.toIntExact(value);
    }
}
~~~

`required` throws an NPE with a clearer message when the input is null; `widen` converts `int` to `long` without value loss; `checkedNarrow` detects a `long` outside the `int` range. These are valid methods under Java 17 that can be compiled with `javac SafeConversions.java`, though there is no `main`, so it is not a self-running program.

## 17. Self-check exercises

**Exercise 1.** Predict the result and explain why:

~~~java
byte x = 127;
x += 1;
System.out.println(x);
~~~

**Answer:** `-128`. Compound assignment allows implicit narrowing; the byte variable overflows in 8-bit representation.

**Exercise 2.** Does the following fail at compile time or runtime?

~~~java
Object o = Integer.valueOf(5);
String s = (String) o;
~~~

**Answer:** Compilation succeeds; at runtime the cast throws `ClassCastException`. The static type of `o` is `Object`, but the actual object is `Integer`.

**Exercise 3.** Does `Long value = 5;` automatically convert int to long and then box?

**Answer:** No. This is a compile-time error. Use `5L` or construct the wrapper from long explicitly.

**Exercise 4.** Why is `Integer n = null; if (n == null) ...` safe while `if (n == 0) ...` can fail?

**Answer:** Comparing a reference with `null` does not unbox; comparing with the primitive numeric `0` requires unboxing `n`, leading to an NPE if n is null.

**Exercise 5.** Should two `Integer` variables both holding value 1000 be compared with `==`?

**Answer:** No. `==` between two references checks identity; `equals` compares numeric value. Do not rely on wrapper caching.

**Exercise 6.** Why is `Object[] a = new String[1]; a[0] = Integer.valueOf(5);` valid at compile time yet fails at runtime?

**Answer:** The static type is `Object[]`, allowing assignment of an `Integer` reference; the actual runtime array is `String[]`, so the JVM throws `ArrayStoreException`.

**Exercise 7.** What is the difference between `(int) Double.POSITIVE_INFINITY` and `Math.toIntExact(Long.MAX_VALUE)`?

**Answer:** Casting floating-point to `int` yields `Integer.MAX_VALUE`, with no exception. `Math.toIntExact` checks whether the `long` value fits in the `int` range and throws `ArithmeticException` if out of range.

## 18. Checklist when encountering conversion-related errors

- Determine the **static type** of each operand; do not look only at the actual object.
- Determine the context: **assignment**, **method invocation**, **casting**, **numeric**, or **conditional expression**.
- Ask which category the conversion belongs to: primitive widening/narrowing, reference widening/narrowing, boxing, unboxing, or a permitted conversion chain.
- If `javac` rejects it, read the type/overload error and check whether it attempts implicit narrowing or widen-then-box.
- If it compiles but fails at runtime, check whether **a reference is `null`**, what type a runtime cast targets, and whether raw generics or array covariance are involved.
- If no exception is thrown yet data is wrong, check for **overflow**, truncation, and precision loss.
- Run a minimal example with `javac --release 17` and then use `javap -c` when you need to observe the conversions the compiler emits.

**Remember:** `javac` verifies **conversions permitted by types**, whereas some conversions are checked against **actual values at runtime**. Automatic boxing makes APIs more convenient, while unboxing nullable values and narrowing reference casts are classic sources of runtime errors. With numeric conversions, the risk is often **value loss without an exception**; to guarantee correctness, check ranges and application requirements.

Standard specification references: [JLS Java SE 17 §5 – Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html), [JLS §15.12 – Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12), [JLS §15.25 – Conditional Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25), and [JLS §10.5 – Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).