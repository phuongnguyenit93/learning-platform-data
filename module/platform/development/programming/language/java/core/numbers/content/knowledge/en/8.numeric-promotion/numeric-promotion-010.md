# `var` infers type from the initializer, not from later usage

When you write `var x = expression;` in Java, the compiler determines the **static type of variable `x` at declaration time** from the type of the **initializer expression**. This type is fixed for the entire scope of the variable. Java **does not** track subsequent assignments, method calls, or later usage to infer a wider type.

```java
var count = 10;   // Static type of count: int
count = 20;       // Valid: int → int
// count = 20L;   // Compile error: long does not auto-narrow to int

var total = 10L;  // Static type of total: long from the start
total = 20L;      // Valid
```

`var` is **compile-time local variable type inference**, not a "type-changing" variable or dynamic typing. This is especially important with **numeric literals**, **operand promotion**, **integer division**, and **overflow**, because Java decides the operation type from the **expression's type**, not from the intent the author expresses later.

## 1. Mechanism: the initializer determines the static type

Consider the declaration:

```java
var result = 1 + 2L;
```

The compiler processes it in the following logical order:

1. Analyze the initializer `1 + 2L`. Literal `1` has type `int`; literal `2L` has type `long`.
2. Apply **binary numeric promotion**: `int + long` produces an expression of type `long`.
3. Infer `result` to have static type `long`, equivalent to the explicit declaration `long result = 1 + 2L;`.
4. For all subsequent statements, `result` is checked as a `long` variable. Java does not re-infer its type when you assign or use it.

You can visualize it as:

```text
initializer → determine expression type → infer variable's static type
                                                      ↓
                                          check all subsequent usages
```

This process happens **at compile time**, before the program runs. For example, `var x = 10;` remains `int` even if later statements execute `x += 1`, `System.out.println(x)`, pass `x` to a method expecting `long`, or add `x` to a `long` to produce a new value.

**Important:** `var` only replaces **manually writing the type name**. All Java rules that normally apply to `int`, `long`, `double`, boxing/unboxing, and type conversions still apply identically.

## 2. What types do numeric initializers produce?

| Declaration | Inferred type | Reason |
| --- | --- | --- |
| `var a = 1;` | `int` | Decimal integer literal without `L` suffix is `int` when in range |
| `var b = 1L;` | `long` | `L` suffix specifies a `long` literal |
| `var c = 1.0;` | `double` | Unsuffixed floating-point literal defaults to `double` |
| `var d = 1.0f;` | `float` | `f` or `F` suffix |
| `var e = (byte) 1;` | `byte` | Expression type after cast is `byte` |
| `var f = (short) 1;` | `short` | Expression type after cast is `short` |
| `var g = 1 + 2L;` | `long` | Promotion inside expression |
| `var h = 1 + 2.0;` | `double` | Operation with `double` |
| `var i = 5 / 2;` | `int` | Integer division yields integer quotient |
| `var j = 5.0 / 2;` | `double` | Has a `double` operand |
| `var k = true ? 1 : 2L;` | `long` | Conditional expression applies `?:` typing rules |
| `var m = Integer.valueOf(7);` | `Integer` | Declared return type of the method is wrapper `Integer` |

The table above shows **there is no "default type of `var`"**: the type depends on the specific initializer.

### Large literals and the `L` suffix

```java
var small = 2_000_000_000;       // int
var big = 3_000_000_000L;        // long
// var invalid = 3_000_000_000; // Does not compile: decimal literal exceeds int
```

`var` does not automatically pick a large enough type for a decimal literal exceeding the `int` range if `L` is omitted. When intending to hold `long`, write an initializer with type `long` from the start (e.g., `3_000_000_000L`), just as in an explicit declaration.

### Conditional expression type is determined before branch selection

```java
var value = true ? 1 : 2L;  // Type long, even though the selected branch yields value 1
```

Java determines the type of `?:` from the types of **both branches** and language rules; it does not wait until runtime to infer from the chosen branch. Looking only at the runtime value `1` is not enough to conclude the variable is `int`.

## 3. "Later usage" does not change the inferred type

```java
var number = 10; // int

long wider = number;       // Valid: widening from int to long
long sum = number + 10L;   // Valid: new expression has type long

// number = 10L;           // Error: no implicit narrowing long → int
// number = 3.14;          // Error: no implicit narrowing double → int
```

In `long wider = number;`, Java only **widens the value upon assignment**; the original type of `number` remains `int`. In `number + 10L`, a **new** expression has type `long` due to operand promotion. The variable `number` itself does not change type.

If data can genuinely exceed the `int` range, declare it properly from the beginning:

```java
var counter = 0L;   // long, can grow up to long range
counter += 3_000_000_000L;
```

The compiler also checks **each assignment** against the inferred type. It does not analyze "all future values" to pick a best-fit type.

### Equivalence to explicit declarations

The two snippets below have the exact same variable types, operations, and conversion rules:

```java
var a = 7;        // int a = 7;
var b = 3L;       // long b = 3L;
var c = a + b;    // long c = a + b;
```

Type inference does not depend on variable names `a`/`b`/`c` or the programmer's expectations about the kind of value.

## 4. `var` does not alter numeric promotion

In Java, for many arithmetic operators such as `+`, `-`, `*`, `/`, and `%`, two integer operands smaller than `int` are promoted at least to `int`; if `long` is present, the integer expression is `long`; if `float`/`double` is present, floating-point promotion rules apply.

```java
byte first = 10;
byte second = 20;

var sum = first + second;  // int, not byte
var product = first * second; // int
var diff = first - second; // int
```

Using `var` on the receiving variable **does not prevent numeric promotion**. The expression `first + second` itself has type `int`.

### Integer division still truncates the fractional part

```java
var ratio = 5 / 2;          // int, value 2
var ratioLong = 5L / 2;     // long, value 2L
var ratioDouble = 5.0 / 2;  // double, value 2.5
```

If you want a fractional result, make **at least one operand** a floating-point type **before division**. Writing `var ratio = 5 / 2;` does not make Java pick `double` just because the mathematical result has `.5`.

Similarly, `var decimal = (double) (5 / 2);` infers `double`, yet its value is still `2.0` because the fractional part was already lost in the `int` division before the cast. To get `2.5`, write `(double) 5 / 2` or `5.0 / 2`.

### `int` multiplication can still overflow before inference

```java
var x = 50_000;        // int
var y = 50_000;        // int

var wrong = x * y;       // int, -1794967296 due to int overflow
var correct = (long) x * y; // long, 2500000000
```

Java multiplies `int * int` in 32 bits, where the result can overflow; `var wrong` simply receives the **`int` type and the computed value**. `var` does not automatically check for overflow and does not widen the type just because the result needs more bits. To make the multiplication use `long`, cast **one operand** before multiplying, use a `long` literal early, or use an API like `Math.multiplyFull(int,int)` where appropriate.

Conversely, `var late = (long) (x * y);` infers `long`, **yet the value is the already-overflowed `int` product cast afterward**. Keep two questions separate: "what type does the variable have?" and "did the initializer expression compute accurately?"

## 5. Compound assignment does not make `var` change types

Compound assignments like `+=`, `-=`, `*=`, and `/=` preserve the target variable's type and include the necessary conversion per compound assignment rules. Therefore:

```java
var value = 10;    // int
value += 0.5;      // Valid, but value stays int with value 10
// value = value + 0.5; // Does not compile: right-hand expression is double
```

The statement `value += 0.5` behaves in value like `value = (int) (value + 0.5)` (except that the left-hand expression is evaluated only once). The `.5` is truncated when converting back to `int`. Type inference from the initializer **does not re-run** on compound assignment.

Similar case:

```java
var count = 127; // int, not restricted like byte
count++;         // int

var tiny = (byte) 127; // byte
tiny++;                // byte, can overflow to -128
```

If you need to transition to floating-point or a wider type for a new requirement, create a new variable with the appropriate type and valid initializer rather than expecting the old `var` variable to "widen its type".

## 6. Inference looks at static types of methods and constructors

### Method return values

```java
var rounded = Math.round(3.5);   // long: Math.round(double) returns long
var smaller = Math.round(3.5f);  // int: Math.round(float) returns int
var wrapper = Integer.valueOf(7); // Integer (wrapper), not primitive int
```

`var` infers from the **declared return type of the call**, taking overload resolution and generic inference into account if applicable. It does not look at "whether the runtime value looks like a small integer". `var wrapper = Integer.valueOf(7)` has type `Integer`, so it can participate in boxing/unboxing inside arithmetic expressions; it is still a fixed static type.

### Constructors and the diamond operator (`<>`)

```java
var names = new java.util.ArrayList<String>();
names.add("Java");
// names.add(42);  // Does not compile: ArrayList<String>

var flexible = new java.util.ArrayList<>();
flexible.add("Java");
flexible.add(42); // Valid: inferred here as ArrayList<Object>
```

With `var flexible = new ArrayList<>()`, there is no explicit target type like `List<String>` to constrain the generic parameter. In this case, the type argument is inferred as `Object`; adding elements afterward **does not re-infer it as `String` or `Integer`**.

If you want an API or collection with a specific element type, supply the type argument in the initializer such as `new ArrayList<String>()` or declare the target type explicitly.

Do not treat `var` as a JavaScript-style dynamic typing mechanism. It follows Java's **static type checking**, and types do not mutate at runtime.

## 7. Where can `var` be used, and what initializer does it require?

`var` is supported for **local variable** type inference starting in Java 10 (e.g., inside methods, `for` loops, enhanced `for` loops, and certain try-with-resources resources). Java 11 added support for `var` on lambda parameters when following proper lambda declaration rules. `var` **cannot replace types** for fields, ordinary method parameters, or method return types.

Valid examples:

```java
var counter = 0;
for (var i = 0; i < 3; i++) {
    counter += i;
}

var numbers = new int[] {1, 2, 3};
for (var n : numbers) {
    System.out.println(n);
}
```

The following examples are **commented out because they do not compile**, to clearly illustrate the limits:

```java
// var missing;           // Invalid: no initializer
// var nullOnly = null;   // Invalid: cannot infer type from null
// var array = {1, 2};    // Invalid: bare array initializer has no target type
// var f = x -> x + 1;    // Invalid: lambda has no target functional interface
// var pair1 = 1, pair2 = 2; // Invalid: var cannot declare multiple variables at once

// class Demo {
//     var field = 1;      // Invalid: cannot use var for fields
//     var get() { ... }   // Invalid: cannot use var as return type
// }
```

Alternatives:

```java
var array = new int[] {1, 2};
java.util.function.IntUnaryOperator f = x -> x + 1;
// Or: var f = (java.util.function.IntUnaryOperator) (x -> x + 1);
```

Lambdas and method references require a **target functional interface** to determine parameter/return types; a "bare" lambda initializer alone does not provide enough target type information for a `var` declaration. For `null`, if you truly need to initialize a null reference, use an explicit type (`String s = null;`) instead of `var s = null;`.

**Note:** the examples in this section are **contextual code snippets**, not standalone Java files. A complete runnable program is placed right below.

## 8. Runnable Java 17+ example: types from initializers and arithmetic results

Create the file `VarInferenceDemo.java`:

```java
public class VarInferenceDemo {
    public static void main(String[] args) {
        var count = 1;          // int
        count += 2;
        System.out.println("count: " + count);

        var countLong = 1L;     // long
        countLong = 3_000_000_000L;
        System.out.println("countLong: " + countLong);

        var sum = count + countLong;  // long: int + long
        System.out.println("int + long: " + sum);

        var ratio = 5 / 2;           // int
        var realRatio = 5.0 / 2;     // double
        System.out.println("ratios: " + ratio + ", " + realRatio);

        var first = 50_000;         // int
        var second = 50_000;        // int
        var bad = first * second;   // int overflow
        var good = (long) first * second; // long
        System.out.println("products: " + bad + ", " + good);

        var conditional = true ? 1 : 2L; // long
        System.out.println("conditional: " + conditional);

        var list = new java.util.ArrayList<String>();
        list.add("Java");
        System.out.println("list: " + list);

        var words = new java.util.ArrayList<>(); // ArrayList<Object>
        words.add("text");
        words.add(42);
        System.out.println("diamond: " + words);

        var numbers = new int[] {1, 2};
        System.out.println("array length: " + numbers.length);

        var width = 10;           // int
        width += 0.5;             // int, still 10
        System.out.println("compound +=: " + width);
    }
}
```

Compile and run:

```bash
javac VarInferenceDemo.java
java VarInferenceDemo
```

Stdout:

```text
count: 3
countLong: 3000000000
int + long: 3000000003
ratios: 2, 2.5
products: -1794967296, 2500000000
conditional: 1
list: [Java]
diamond: [text, 42]
array length: 2
compound +=: 10
```

**Key points to read in the output:**

1. `count` stays `int` after `+=`; `countLong` is `long` because of initializer `1L`.
2. `sum` is `long` due to `int + long`, even though the original variable `count` remains `int`.
3. `ratio` has type `int`, so `.5` is discarded in `5 / 2`. `realRatio` has type `double`, so it gets `2.5`.
4. `bad` holds the overflowed `int` multiplication result; `good` computes in `long` because the cast precedes **multiplication**.
5. `conditional` is inferred as `long` from the expression containing branch `2L` at compile time, even though the program prints `1`.
6. `list` and `words` have their generic types fixed at declaration; adding elements later does not cause Java to re-infer type parameters.
7. `width += 0.5` still stores the result back as `int`, because compound assignment does not change a variable's type.

## 9. When to use `var` and when to write the type explicitly

`var` is helpful when the initializer makes the type immediately obvious:

```java
var total = 0L;
var ratio = (double) numerator / denominator;
var names = new java.util.ArrayList<String>();
```

The second example is a snippet inside a method: `numerator` and `denominator` must already be declared. The `(double)` cast expresses the intent of floating-point division right in the initializer, avoiding misinterpreting what `var` infers.

Explicit type declarations are often clearer when **numeric range and precision matter**, for example:

```java
long transactionCount = 0L;
double probability = 0.0;
int maxRetries = 3;
```

Not because `var` is less safe; both forms follow the exact same compiler rules. Explicit types help readers immediately see the data contract, especially when the initializer is a dense expression or a complex generic/overloaded call.

Some practical guidelines:

- **Shape the type right in the initializer.** Want `long`? Use `0L` or a `long` expression; want floating-point division? Use a floating-point literal/cast before dividing.
- **Evaluate intermediate types**, especially with `int * int`, `int / int`, and chained operations.
- **Keep initializers clear**, avoiding relying on actual runtime values to guess types.
- **Specify the right collection type upon creation**, since `var` combined with diamond `<>` can infer `Object` if constraints are insufficient.
- **Use variable names that convey units/meaning**, such as `timeoutMillis`, `priceCents`, or `ratio`; clear static types and meaningful names work together to prevent mistakes.

## 10. Common misconceptions

1. **"`var` is a dynamic type; a variable can change to `long` when assigned a big number."** False: `var x = 1` fixes `x` as `int` at compile time.
2. **"Java looks at later assignments to infer `var`'s type."** False: only the initializer at declaration decides the inferred type.
3. **"`var` automatically prevents `int` overflow because no type is declared."** False: an `int * int` expression still computes in `int`.
4. **"`var r = 5 / 2` becomes `double` since 2.5 is the mathematical result."** False: `5 / 2` is `int` with value 2.
5. **"`var v = (long) (a * b)` is guaranteed to preserve the product."** False: the `int` multiplication may have already overflowed before the cast.
6. **"After `x += 0.5`, variable `x` changes to `double`."** False: compound assignment converts the result back to `x`'s static type, potentially losing the fractional part.
7. **"`var list = new ArrayList<>()` infers `String` because a string is added first."** False: type arguments are not re-inferred from later `add` calls.
8. **"`var x = null` is valid because Java can choose `Object`."** False: a bare null initializer does not provide a usable type for inference.
9. **"`var f = x -> x + 1` can infer the functional interface from the lambda body."** False: lambdas require a target type.
10. **"`var` can replace every type declaration in a class."** False: `var` has scope restrictions per language rules, mainly local declarations with initializers and a few specific positions.
11. **"With `var`, `long a = 1 + 2L` and `var a = 1 + 2L` have different types."** False: in this example both variables have type `long`.
12. **"The printed value of `conditional` is 1, so its type must be `int`."** False: `true ? 1 : 2L` has type `long` due to conditional expression rules.

## 11. Self-check

- Does `var n = 100; n = 100L;` compile? **No**: `n` is `int` from initializer `100`, so `long` cannot be assigned directly.
- Does `var n = 100L; n = 200;` compile? **Yes**: the `int` value 200 is widened to `long` on assignment.
- What is the type and value of `var x = 7 / 2;`? **`int` and 3**, because integer division truncates toward 0.
- What is the type and value of `var y = 7.0 / 2;`? **`double` and 3.5**.
- What is the type of `var p = 50_000 * 50_000;`? **`int`**, which has already overflowed before being stored. To get the accurate `long` value, write `var p = 50_000L * 50_000;`.
- What is the type of `var z = true ? 1 : 2L;`? **`long`**, because Java checks the type of the whole conditional expression.
- Does `var words = new ArrayList<>();` change to `ArrayList<String>` after calling `words.add("hi")`? **No**.
- When a `long` bound is required to avoid exceeding the `int` range, what is the significance of putting `L` in the initializer? **It specifies the literal's type and can change the type of the entire expression before the operation runs**.

**Takeaway:** `var` lets **the compiler write the variable type for you**, and that type is determined **once from the initializer alone**. `var` does not look ahead at later lines and does not change Java's numeric promotion, overflow, division, or assignment rules. Put the intended type into the **initializer/operand types before the calculation**, and verify value ranges properly.