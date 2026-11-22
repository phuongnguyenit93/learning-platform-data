# Autoboxing and Contexts for Converting Primitives to Wrappers in Java

## 1. What is autoboxing?

In Java, **primitives** are the primitive data types such as `int`, `long`, `double`, and `boolean`; whereas **wrappers** are classes that encapsulate a corresponding primitive value into an object. **Autoboxing** is the automatic application of a *boxing conversion* by the compiler in contexts Java permits, so that a primitive value can be used where a wrapper object is expected.

```java
int primitive = 42;
Integer boxed = primitive;  // Autoboxing: int -> Integer.
int again = boxed;          // Unboxing: Integer -> int.

System.out.println(boxed);  // 42
System.out.println(again);  // 42
```

Semantically, `Integer boxed = primitive` is close to `Integer.valueOf(primitive)`. Java does not require you to write `new Integer(...)` (the old wrapper constructors have been deprecated and should not be used); you can let the compiler generate the necessary conversion. However, **autoboxing does not mean Java turns any numeric type into any numeric class arbitrarily**; the conversion must be valid according to the exact context and target type.

Notable examples:

- A `List<Integer>` only accepts elements that are `Integer` references, yet you can call `list.add(5)`; Java boxes `5` into an `Integer`.
- A method accepting `Double` can be called with the `double` literal `1.5` thanks to boxing.
- A variable `Number n = 5;` is valid: Java **boxes `int` to `Integer`, then widens the reference** to `Number`.
- Conversely, `Long x = 5;` is **not** valid: Java does not automatically chain `int -> long -> Long` in a normal assignment. You need `5L` or an explicit conversion.

## 2. Complete mapping table between the eight primitives and wrappers

| Primitive | Wrapper | Autoboxing example | Explicit creation |
| --- | --- | --- | --- |
| `boolean` | `Boolean` | `Boolean b = true;` | `Boolean.valueOf(true)` |
| `byte` | `Byte` | `Byte b = (byte) 5;` | `Byte.valueOf((byte) 5)` |
| `short` | `Short` | `Short s = (short) 5;` | `Short.valueOf((short) 5)` |
| `char` | `Character` | `Character c = 'A';` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer n = 5;` | `Integer.valueOf(5)` |
| `long` | `Long` | `Long n = 5L;` | `Long.valueOf(5L)` |
| `float` | `Float` | `Float f = 1.5f;` | `Float.valueOf(1.5f)` |
| `double` | `Double` | `Double d = 1.5;` | `Double.valueOf(1.5)` |

The `void` type has a related `Void` class in the API, but **there is no `void` value to autobox** like the eight primitives in the table above.

**Wrappers are objects and can be `null`**, whereas primitive variables cannot hold `null`. Wrappers are designed to be **immutable**: an `Integer` object holding `5` does not have its value changed to `6`; an increment operation on a wrapper variable will unbox, compute, and box a value again.

## 3. Assignment context: variables, fields, and array elements

### 3.1. Assigning a primitive to a wrapper

```java
int quantity = 7;
Integer quantityObject = quantity;

double price = 19.5;
Double priceObject = price;

boolean enabled = true;
Boolean enabledObject = enabled;
```

In all three cases, the assignment has a target type of the corresponding wrapper, so Java automatically boxes the value. The same mechanism applies to initializing fields or reassigning a wrapper variable.

Example of field declarations in a class:

```java
class Product {
    Integer stock = 10;   // The int literal is autoboxed.
    Boolean active = true; // The boolean literal is autoboxed.
}
```

This is a syntactically standalone illustrative class; a `main` method is not required to demonstrate that boxing is valid.

### 3.2. Boxing followed by widening reference conversion

```java
Number number = 123; // int -> Integer -> Number.
Object object = 2.5; // double -> Double -> Object.

System.out.println(number.getClass().getSimpleName()); // Integer
System.out.println(object.getClass().getSimpleName()); // Double
```

This is a *boxing conversion* combined with a *widening reference conversion*. The static type of the variable is `Number` or `Object`, but the object created/obtained after boxing still belongs to the concrete wrapper class.

Therefore, you should not infer from `Number n = 123` that Java creates a “Number object” directly. `Number` is an abstract class; the value `123` in the example is wrapped as an `Integer`.

### 3.3. Initializing a wrapper array

```java
Integer[] scores = {10, 20, 30}; // Each element is boxed.
Double[] rates = {0.5, 1.5};    // double -> Double.
```

**There is no automatic conversion from an entire primitive array to a wrapper array**:

```java
int[] raw = {1, 2, 3};
// Integer[] boxedArray = raw; // Compile-time error.
```

If you need to convert an entire array, you must do it **element by element** or use an appropriate API, such as `IntStream.of(raw).boxed().toArray(Integer[]::new)`. Autoboxing is not a “retype the whole container” mechanism.

## 4. Method invocation context: passing primitive arguments

A method declaring a wrapper parameter can be called with a primitive argument of the same type:

```java
static void acceptInteger(Integer value) {
    System.out.println(value);
}

static void acceptDouble(Double value) {
    System.out.println(value);
}

// When called in other code of the same class:
// acceptInteger(8);    // int -> Integer.
// acceptDouble(2.5);   // double -> Double.
```

In a method invocation context, the compiler determines the applicable method according to the phases of **overload resolution**. Boxing is permitted in the appropriate phases; however, not every conversion chain is allowed and an overload accepting a wrapper is not always preferred.

### Overload: primitive widening is considered before boxing

```java
static void pick(long value) {
    System.out.println("long");
}

static void pick(Integer value) {
    System.out.println("Integer");
}

// pick(1); // Prints "long": int -> long is considered in the strict invocation phase.
```

For the `int` literal `1`, `pick(long)` is applicable via *widening primitive conversion* without boxing; `pick(Integer)` requires boxing. Java resolves methods in the phase allowing non-boxing conversions first, so the example above chooses `pick(long)`.

Practical takeaway: **do not design an API based solely on the intuition that Java will prefer a “closer” wrapper**. When overloads mix primitives, wrappers, varargs, and reference types, read the method signatures and understand the selection order; if it is hard to read, cast or pass the explicit value.

### Wrapper varargs can also receive primitive values

```java
static void acceptMany(Integer... values) {
    System.out.println(values.length);
}

// acceptMany(1, 2, 3); // Prints 3: each int is boxed into Integer.
```

Varargs is a mechanism for creating/receiving a parameter array, **not for boxing an entire `int[]` array**. Calling `acceptMany(rawIntArray)` with an `int[]` will not become a valid `Integer[]` via autoboxing alone.

## 5. Return values, lambdas, and generics

### Return statement

A method declared to return a wrapper can return a primitive when the conversion is valid:

```java
static Integer boxedResult(int input) {
    return input; // int -> Integer in return context.
}
```

Conversely, a method returning `int` can `return` a non-null `Integer` thanks to unboxing, but it will throw `NullPointerException` if the returned wrapper value is `null`.

### Lambdas returning a wrapper

```java
import java.util.function.Supplier;

Supplier<Integer> supplier = () -> 42;
System.out.println(supplier.get()); // 42
```

The target of the lambda is a functional interface with an `Integer` result. The expression `42` is boxed to satisfy the return type. This is useful when modern code uses `Supplier`, `Function`, or other generic functional interfaces.

### Generics only accept reference types

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>();
values.add(10); // int -> Integer.
values.add(20); // int -> Integer.

// List<int> invalid = new ArrayList<>(); // Compile-time error.
```

A generic type parameter like `T` in `List<T>` must be a reference type, not a primitive. Wrapper classes allow numeric data to be used in generics.

You also need to distinguish `List<Integer>` from `List<Number>`: they **do not have a direct subtype relationship** due to generic invariance rules, even though `Integer` extends `Number`. Autoboxing does not turn `List<Integer>` into `List<Number>`.

## 6. Conversions Java does not perform automatically

Autoboxing does **not** mean any primitive can be assigned to any numeric wrapper. Both the context and the conversion chain matter.

```java
Integer a = 10; // Valid: int -> Integer.
Long b = 10L;   // Valid: long -> Long.
Double c = 1.0; // Valid: double -> Double.

// Long invalid = 10;   // Invalid: does not automatically chain int -> long -> Long.
// Double bad = 1;      // Invalid: does not automatically chain int -> double -> Double.
```

Ways to make it explicit:

```java
long widened = 10; // int -> long.
Long wrapped = widened; // long -> Long.
// Or:
Long also = 10L;
```

Similarly, Java does not automatically convert one wrapper to another wrapper by assignment:

```java
Integer input = 10;
// Long invalid = input; // Does not compile.
Long converted = input.longValue(); // long -> Long.
```

Note an exception in **constant assignment contexts**: Java allows narrowing a constant `int` expression within the range of `byte`, `short`, or `char`, followed by boxing into the corresponding wrapper. For example:

```java
Byte small = 100; // Valid: constant int 100 is within byte range.
Short shortValue = 123; // Valid.
// Byte outside = 200; // Error: 200 is outside byte range.
```

This is a special rule about **constant expressions and assignment conversion**, not evidence that Java automatically allows arbitrary numeric conversions followed by boxing. With a regular `int` variable, `Byte boxed = someInt;` is invalid without an explicit cast step.

## 7. Autoboxing and unboxing in arithmetic expressions

When a wrapper appears in an arithmetic operation, Java usually must **unbox** it to obtain the primitive, then apply the expression's numeric promotion rules.

```java
Integer a = 7;
Integer b = 5;

int sum = a + b; // Unbox a,b -> int; int addition yields 12.
Integer boxedSum = a + b; // Compute int addition, then box 12.
```

The statement `Integer boxedSum = a + b` **does not mean two `Integer` objects are added directly together**. The values must be extracted from the wrappers, primitive addition performed, and only then is the result boxed for assignment.

### Compound assignment and incrementing/decrementing wrappers

```java
Integer count = 7;
Integer original = count;

count += 5; // Unbox -> int addition -> box back to Integer.
count++;    // Unbox -> add 1 -> box again.

System.out.println(original); // 7
System.out.println(count);    // 13
```

The `original` object still holds `7` because wrappers are **immutable**. After the operations, the `count` variable holds a reference to the newly boxed result object (or a reused object from the cache), rather than mutating the old object's value.

These operations are still subject to primitive range limits:

```java
Integer max = Integer.MAX_VALUE;
max++; // int addition exceeds limit and wraps around.
System.out.println(max); // -2147483648
```

Boxing does not automatically add overflow checks. If overflow is not allowed, use `Math.addExact` or appropriate bounds checks before boxing the result.

## 8. Crucial trap: wrappers can be `null`

Primitives cannot be `null`, wrappers can:

```java
Integer optionalCount = null;

// int count = optionalCount; // Throws NullPointerException at runtime.
```

There is no `int` value corresponding to `null`. Whenever Java needs to **unbox a null reference**, the program throws `NullPointerException`.

Common scenarios:

```java
Integer a = null;

// int x = a;         // NPE on unbox.
// int y = a + 1;     // NPE before addition.
// a++;               // NPE on unbox.
// boolean eq = a == 0; // NPE when comparing with primitive 0.
```

Meanwhile, **boxing a valid primitive does not create null on its own**; the risk here arises from places where a wrapper may hold null.

An explicit way to handle it:

```java
Integer count = null;
int safe = count != null ? count : 0;
System.out.println(safe); // 0
```

The `null -> 0` rule must be a **business decision**, not the default of auto-unboxing. If null means “unknown”, “not entered”, or “not applicable”, replacing it with 0 can corrupt data. When you need to preserve the missing-data state, use a wrapper/Optional or report an explicit error instead of forcing it to a primitive.

If a wrapper is passed through a `List<Integer>` or `Map<String, Integer>`, the retrieved data can still be `null`. Autoboxing when adding elements does not guarantee every subsequent read is safe to unbox.

## 9. Wrappers and `==`: do not use identity as numeric comparison

When **both operands are wrapper references**:

```java
Integer first = Integer.valueOf(1_000);
Integer second = Integer.valueOf(1_000);

System.out.println(first.equals(second)); // true
```

A wrapper's `equals` method compares **values according to the class contract**, whereas `first == second` compares **whether they are the same object**. Do not use `==` between two wrappers as the criterion for numeric equality.

There is an object **caching/reuse** mechanism when boxing certain small values. For example, for `Integer`, the value `100` falls within the range guaranteed to be reused during boxing:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b); // true per boxing guarantee for this value.
```

However, for larger values, object reuse depends on rules and implementation, so you must not write:

```java
Integer x = 1_000;
Integer y = 1_000;

// boolean equalNumbers = (x == y); // Do not use: identity comparison.
boolean equalNumbers = x.equals(y); // true.
```

**Do not assume every value outside the cache always returns false with `==`**; an implementation may reuse some objects. Use `equals` when you want to compare wrappers of the same type, or unbox with a null check if you want to compare primitives.

When one side is a primitive:

```java
Integer boxed = 5;
int primitive = 5;
System.out.println(boxed == primitive); // true, boxed is unboxed.
```

Here `==` is a primitive value comparison, not a reference identity comparison. This difference explains why changing a variable's declared type can accidentally change the meaning of the same `==` symbol.

Note that with `Float`/`Double`, the `equals` contracts also differ from primitive `==` for `NaN` and `+0.0`/`-0.0` values. When using wrappers as `HashMap`/`HashSet` keys, collections rely on `equals` and `hashCode`, not primitive `==` comparison.

## 10. Impact on performance and memory

Wrapper types are **objects**, so they can require extra memory, object allocation/management, and conversions compared to working directly with primitives. The compiler/JVM can optimize many cases, but you should not assume autoboxing is “free” in all hot loops or large datasets.

Example:

```java
long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // Entire computation path uses primitives.
}
```

Compared to:

```java
Long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // Unboxing and re-boxing total on every iteration.
}
```

This is an example to recognize **the conversions semantically required**, not a benchmark asserting exact speeds. Actual performance depends on the JVM, JIT optimizations, escape analysis, data size, and measurement methodology.

When you need to process many integers, consider:

- Using `int[]`/`long[]`/`double[]` instead of wrapper arrays if you do not need `null` or object APIs.
- Using `IntStream`, `LongStream`, `DoubleStream` for primitive data pipelines; calling `boxed()` only when converting to `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`.
- Using `List<Integer>` or wrappers when generic APIs, optional/nullable data, and collection structures require objects.

**Do not optimize prematurely:** prioritize correctness and clarity, then use a proper benchmark (such as JMH) to verify costs in the parts of the program that actually matter.

## 11. Do not confuse autoboxing with every implicit conversion

There are situations that look like “turning a number into an object” or “printing a number to the screen” that **do not require autoboxing to occur**:

```java
System.out.println(10);          // Has a println(int) overload.
String message = "count=" + 10; // String concatenation has string conversion rules.
```

You cannot take these two lines as proof that every primitive is always turned into a wrapper. Autoboxing is a conversion applied in specific typing contexts; string concatenation and overload selection can work without creating wrappers.

Similarly, ordinary reference casting and autoboxing are two different things. Writing `Number number = 10;`, which creates an `Integer` and then widens the reference type, does not mean `Number` is a direct wrapper class for `int`. And calling `Integer.valueOf("10")` is **parsing a string and creating an Integer**, not autoboxing a `String` value.

## 12. Complete Java 17+ example

Create the file **`AutoboxingContextsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class AutoboxingContextsDemo {
    static void receive(Integer value) {
        System.out.println("method=" + value);
    }

    static void choose(long value) {
        System.out.println("overload=long");
    }

    static void choose(Integer value) {
        System.out.println("overload=Integer");
    }

    static Integer boxReturn(int input) {
        return input;
    }

    public static void main(String[] args) {
        int primitive = 7;
        Integer boxed = primitive;
        int unboxed = boxed;

        System.out.println("assignment=" + boxed);
        System.out.println("unboxed=" + unboxed);

        receive(8); // Parameter autoboxing.
        choose(1);  // Primitive widening takes priority over boxing.

        Object object = 2.5;
        Number number = 6;
        System.out.println("Object holds="
                + object.getClass().getSimpleName());
        System.out.println("Number holds="
                + number.getClass().getSimpleName());

        Integer[] array = {2, 3};
        System.out.println("array second=" + array[1]);

        List<Integer> values = new ArrayList<>();
        values.add(4);
        values.add(5);
        int sum = 0;
        for (int value : values) {
            sum += value; // Unbox each Integer.
        }
        System.out.println("list=" + values);
        System.out.println("list sum=" + sum);

        System.out.println("return boxed=" + boxReturn(12));

        Supplier<Integer> supplier = () -> 13;
        System.out.println("lambda boxed=" + supplier.get());

        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("small cached identity=" + (smallA == smallB));

        Integer largeA = 1_000;
        Integer largeB = 1_000;
        System.out.println("large equals=" + largeA.equals(largeB));

        Integer current = 7;
        Integer previous = current;
        current += 5;
        System.out.println("updated=" + current);
        System.out.println("previous=" + previous);

        Integer missing = null;
        try {
            int willFail = missing;
            System.out.println(willFail);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac AutoboxingContextsDemo.java
java AutoboxingContextsDemo
```

Output:

```text
assignment=7
unboxed=7
method=8
overload=long
Object holds=Double
Number holds=Integer
array second=3
list=[4, 5]
list sum=9
return boxed=12
lambda boxed=13
small cached identity=true
large equals=true
updated=12
previous=7
null unboxing=NullPointerException
```

The example demonstrates five conversion groups: **assignment**, **method arguments**, **arrays/generic collections**, **return values/lambdas**, and **unboxing in operations**. It does not rely on identity comparison results for large values outside the cache region; it only uses `equals` for that case.

## 13. Common mistakes and how to avoid them

| Misconception | Why it is wrong | Correct approach |
| --- | --- | --- |
| “Autoboxing converts any primitive to any wrapper.” | Boxing maps to the corresponding wrapper and is restricted by conversion context. | Choose the right literal type, use a cast, or convert explicitly when needed. |
| “`Long x = 5` is definitely valid because `int` widens to `long`.” | Assignment does not automatically chain `int → long → Long`. | `Long x = 5L` or convert via a `long` variable. |
| “`List<int>` can be used like `List<Integer>`.” | Generic type parameters must be reference types. | Use `List<Integer>` or primitive structures. |
| “`int[]` will autobox to `Integer[]`.” | Boxing does not apply directly to an entire array. | Convert element by element. |
| “Wrappers are always non-null because of autoboxing.” | Reference variables/collections can hold `null`. | Check for null before unboxing. |
| “`Integer a == Integer b` always compares numeric values.” | If both are references, `==` compares identity. | Use `equals` or unbox safely. |
| “Outside the cache range, `==` is guaranteed false.” | Wrapper reuse outside the guaranteed range must not be assumed. | Do not rely on the identity of boxed numbers. |
| “`Integer count++;` mutates the `Integer` object in place.” | Wrappers are immutable; the operation unboxes, computes, then boxes and reassigns. | Clearly understand the primitive types inside the operation. |
| “Autoboxing prevents integer arithmetic overflow.” | Arithmetic still uses primitives and obeys their limits. | Check bounds/`Math.*Exact` if the contract forbids overflow. |
| “Every place printing numbers/building strings allocates wrappers.” | Primitive overloads and string conversions do not equate to boxing. | Check the actual API and expression types. |
| “Using wrappers in loops cannot have any cost.” | Conversions and object management can incur overhead. | Use primitives when appropriate, measure performance before optimizing. |

## 14. Checklist when applying autoboxing in source code

1. **Source/target types:** Which primitive is being converted to which wrapper? Is primitive widening or narrowing needed before boxing?
2. **Context:** Does assignment, return, method call, lambda, or generic collection permit that conversion?
3. **Nullability:** Where does this wrapper come from? Could it be `null` during unboxing?
4. **Comparison:** Do you need value comparison `equals` or object identity `==`? If `Float`/`Double`, do NaN/signed zero cases matter?
5. **Overloading:** If the same method name has primitive and wrapper parameters, which overload is chosen by the resolution phases?
6. **Precision and bounds:** Boxing only wraps the value; it does not fix overflow or recover floating-point rounding errors.
7. **Cost:** Does the generic structure truly need wrappers, or are primitive types/arrays/primitive streams sufficient?
8. **API/clarity:** When in doubt, use `Integer.valueOf`, `longValue()`, explicit casts, or split statements to make conversions clear.

**Key takeaway:** Autoboxing is a conversion automatically provided by Java from a **primitive to its corresponding wrapper in permitted typing contexts**. It is convenient for object APIs and generics, but it does not create new numeric types, does not handle overflow, does not automatically guarantee a wrapper is non-`null`, does not change identity comparison rules, and can carry performance costs. Understanding the exact timing of boxing/unboxing helps prevent compile-time errors, `NullPointerException`, and subtle bugs when handling numbers.

**References:** [JLS §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7), [JLS §5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [JLS §5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.2), [JLS §5.3 — Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3), [JLS §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2), [Integer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
