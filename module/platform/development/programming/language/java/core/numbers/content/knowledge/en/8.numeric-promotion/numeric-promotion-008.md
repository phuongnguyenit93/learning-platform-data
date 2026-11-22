# Unboxing when expressions contain wrappers in Java

## 1. Why can an expression containing `Integer` throw an error?

Java has **primitive types** such as `int`, `long`, `double`, `boolean`, and corresponding **wrapper classes** such as `Integer`, `Long`, `Double`, `Boolean`. Wrappers are objects and can hold a `null` reference; primitives store a primitive value and cannot be `null`.

**Unboxing** is when Java automatically converts a wrapper's value into its corresponding primitive when the context requires a primitive. Example:

```java
Integer boxed = 10;
int primitive = boxed; // unboxing: Integer -> int
```

Conversely, **boxing** converts a primitive value into a wrapper:

```java
int primitive = 10;
Integer boxed = primitive; // boxing: int -> Integer
```

In an arithmetic operation, Java can perform a chain of steps: **unboxing → numeric promotion → computation → (if needed) boxing when assigning the result**. Therefore, seeing operands of type `Integer` does not mean addition produces an `Integer` or that addition happens directly between objects.

Direct example:

```java
Integer left = 7;
Integer right = 5;

int sum = left + right;      // unbox both, int addition -> 12
Integer boxedSum = left + right; // unbox, int addition, box result -> 12
```

If a wrapper is unboxed while it is `null`, Java throws **`NullPointerException` (NPE)**. It does not treat `null` as 0, `false`, or any default value.

## 2. Identifying primitives and wrapper classes accurately

| Primitive | Wrapper | Can wrapper value be `null`? | When unboxed |
|---|---|---|---|
| `byte` | `Byte` | Yes | Corresponding `byteValue()` |
| `short` | `Short` | Yes | Corresponding `shortValue()` |
| `int` | `Integer` | Yes | Corresponding `intValue()` |
| `long` | `Long` | Yes | Corresponding `longValue()` |
| `float` | `Float` | Yes | Corresponding `floatValue()` |
| `double` | `Double` | Yes | Corresponding `doubleValue()` |
| `char` | `Character` | Yes | Corresponding `charValue()` |
| `boolean` | `Boolean` | Yes | Corresponding `booleanValue()` |

The phrase "corresponding" is a mental model for the conversion process; source code normally just writes natural expressions, such as `boxed + 1`. Java performs the necessary conversion according to the context's rules.

Situations where wrappers are useful include generic types such as `List<Integer>` (Java generics do not accept `List<int>`), APIs that allow missing data as `null`, or libraries requiring objects. When performing pure calculations without needing `null` capability, primitives are usually clearer.

## 3. Unboxing in addition, subtraction, multiplication, and division

When an arithmetic operator requires a numeric type, wrappers are unboxed first. For integral types, Java then applies **binary numeric promotion**:

- `Byte`, `Short`, and `Character` after unboxing are promoted to `int` when used with binary arithmetic operators.
- `Integer` after unboxing becomes `int`.
- If there is a `Long` or `long` operand, the integral expression uses `long`.
- With `Float`/`Double` or `float`/`double`, the result follows the corresponding floating-point promotion rules.

Example:

```java
Integer a = 10;
Integer b = 5;
Long wide = 2L;
Short small = 3;

int sum = a + b;           // int 15
int difference = a - b;    // int 5
int product = a * b;       // int 50
int quotient = a / b;      // int 2
long mixed = a + wide;     // long 12
int promoted = small * 4;  // int 12
```

How to trace `a + wide`:

1. `a` is unboxed to `int` 10.
2. `wide` is unboxed to `long` 2.
3. `int` 10 is promoted to `long` 10.
4. `long` addition yields **`long` 12**.

**The result type is determined by the operator and promotion rules**. The wrapper type of the receiving variable can only trigger boxing **after computation**:

```java
Integer first = 10;
Integer second = 20;
Integer result = first + second; // int + int -> int 30 -> Integer
Long largeResult = first + 20L;  // int + long -> long 30 -> Long
```

Integer addition can still **overflow** just like with primitives. `Integer.MAX_VALUE + 1` computed in `int` still becomes `Integer.MIN_VALUE`; wrappers do not expand value ranges.

## 4. Java 17+ program: seeing types and NPE

Save as `UnboxingArithmeticDemo.java`:

```java
public class UnboxingArithmeticDemo {
    private static String typeOf(int ignored) {
        return "int";
    }

    private static String typeOf(long ignored) {
        return "long";
    }

    public static void main(String[] args) {
        Integer count = 7;
        Long increment = 5L;
        Short factor = 3;

        System.out.println("int addition: " + (count + 2));
        System.out.println("mixed result: " + (count + increment));
        System.out.println("type int: " + typeOf(count + 2));
        System.out.println("type long: " + typeOf(count + increment));
        System.out.println("short product: " + (factor * 4));

        Integer boxedSum = count + 2;
        System.out.println("boxed sum: " + boxedSum);

        Integer nullable = null;
        System.out.println("string concat: " + nullable);

        try {
            int invalid = nullable + 1;
            System.out.println(invalid);
        } catch (NullPointerException e) {
            System.out.println("arithmetic: NullPointerException");
        }

        try {
            nullable++;
        } catch (NullPointerException e) {
            System.out.println("increment: NullPointerException");
        }
    }
}
```

Run on Java 17+:

```bash
javac UnboxingArithmeticDemo.java
java UnboxingArithmeticDemo
```

Output:

```text
int addition: 9
mixed result: 12
type int: int
type long: long
short product: 12
boxed sum: 9
string concat: null
arithmetic: NullPointerException
increment: NullPointerException
```

The two `typeOf` overloads serve as a tool to demonstrate the **compile-time type of the expression**. For `count + 2`, Java picks the `int` overload; for `count + increment`, Java picks `long`.

One notable point: `"string concat: " + nullable` is **string concatenation**, so the `null` reference value is represented by the text `"null"`. Conversely, `nullable + 1` needs a numeric value, leading to unboxing and NPE. Both expressions use `+` yet belong to **two different contexts**.

## 5. Assignment and compound assignment

### 5.1. Assigning a primitive from a wrapper

```java
Integer boxed = 42;
int number = boxed; // unboxing
```

If `boxed == null`, the assignment above throws NPE. If you want to default to 0 when the value is missing:

```java
Integer boxed = null;
int number = boxed != null ? boxed : 0; // 0
```

The conditional expression evaluates only the selected branch. Here the `boxed` branch is chosen only when non-`null`; therefore unboxing is safe under this condition.

### 5.2. `+=`, `-=`, `*=`, and `++` can also unbox

```java
Integer count = 10;
count += 5; // unboxing -> int addition -> boxing, count = 15
count++;    // unboxing -> int increment -> boxing, count = 16
```

`Integer` is an **immutable object**. Update operations on a wrapper variable do not mutate the value inside the same object; Java computes a primitive value and reassigns an appropriate wrapper reference.

If `count` is `null`, then `count += 5` or `count++` requires unboxing and throws NPE. You cannot rely on `+=` syntax to treat null as 0.

### 5.3. Assigning the result to another wrapper type must follow conversion rules

```java
Integer a = 10;
Long b = 20L;

Long total = a + b; // valid: long 30 -> Long
// Long invalid = a + a; // compile error: int -> Long is not a valid assignment conversion chain
long primitiveTotal = a + a; // valid: int 20 -> long
```

The commented line illustrates a limitation: Java does not automatically combine **widening primitive `int` to `long` and then boxing to `Long`** in an ordinary assignment from an `int` expression. If a `Long` is needed, perform the operation in `long`, e.g., `Long total = (long) a + a;`.

## 6. Comparisons: when does `==` unbox, and when does it compare references?

The `==` operator has different rules depending on operand types.

### 6.1. Wrapper compared to a numeric primitive: unboxing occurs

```java
Integer boxed = 10;
boolean equal = boxed == 10; // true, boxed is unboxed
```

If `boxed` is `null`, the expression `boxed == 10` can throw NPE because it must unbox before the numeric comparison.

```java
Integer boxed = null;
boolean isMissing = boxed == null; // true, reference comparison, safe
// boolean zero = boxed == 0;     // throws NullPointerException at runtime
```

**`boxed == null` does not unbox**, because it is comparing a reference with `null`. That is a valid way to check for missing data.

### 6.2. Two wrappers of the same type: compares references

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);

boolean sameReference = a == b; // reference comparison; do not rely on true/false
boolean sameValue = a.equals(b); // true
```

When both operands are `Integer`, `==` checks **whether they are the same object**. Because wrappers can reuse cached objects, `==` sometimes returns `true` for equal values; **that is not a reliable rule for value comparison**.

Use `a.equals(b)` for value comparison when `a` is known to be non-`null`, or `java.util.Objects.equals(a, b)` when one or both may be `null`:

```java
Integer a = null;
Integer b = null;

System.out.println(java.util.Objects.equals(a, b)); // true
System.out.println(java.util.Objects.equals(a, 0)); // false
```

Furthermore, comparing two wrappers of **different types** such as `Integer` and `Long` has restrictions on reference comparability in `==` expressions. When the goal is comparing numeric values, decide the intended numeric type and convert explicitly with checks, instead of expecting `==` to compare all wrapper types by value.

### 6.3. Relational comparisons `<`, `>`, `<=`, `>=`

Relational operators require numeric values, so numeric wrappers are unboxed:

```java
Integer min = 3;
Long max = 7L;

System.out.println(min < max); // true
```

If an operand needing unboxing is `null`, Java throws NPE. The safe approach is checking for null first or establishing a default/rejection policy for missing data.

## 7. `Boolean` in conditions and logical operators

The `Boolean` wrapper can represent three states at the reference level: `Boolean.TRUE`, `Boolean.FALSE`, and `null`. However, an `if` condition or `while` loop requires a **primitive `boolean` value**.

```java
Boolean enabled = Boolean.TRUE;
if (enabled) { // unbox Boolean -> boolean
    System.out.println("enabled");
}
```

If `enabled == null`, `if (enabled)` throws NPE.

Similarly, the operators `!`, `&&`, and `||` when needing a `boolean` value can also unbox wrappers:

```java
Boolean flag = null;
// boolean inverted = !flag;    // NullPointerException
// boolean result = flag && true; // NullPointerException
```

### Null checking with short-circuiting

The `&&` and `||` operators **short-circuit**: the right branch is evaluated only when needed.

```java
Boolean flag = null;

boolean safeEnabled = flag != null && flag; // false, does not unbox null
boolean alsoSafe = Boolean.TRUE.equals(flag); // false
```

With `flag != null && flag`, the left side is false, so the right side is not evaluated. With `Boolean.TRUE.equals(flag)`, the method is called on the `Boolean.TRUE` object rather than on null; it returns false if flag is null.

The two ways express different application policies: treating null as false can make sense for optional flags, but **never** default null to false when null means "unverified", "not entered", or "unknown". In such cases, handle the missing-data state explicitly.

## 8. Java 17+ program: null-safe comparisons and conditions

Save the file `UnboxingConditionsDemo.java`:

```java
import java.util.Objects;

public class UnboxingConditionsDemo {
    public static void main(String[] args) {
        Boolean enabled = null;
        Integer limit = null;

        System.out.println("enabled == null: " + (enabled == null));
        System.out.println("Boolean.TRUE.equals: "
                + Boolean.TRUE.equals(enabled));
        System.out.println("short circuit boolean: "
                + (enabled != null && enabled));
        System.out.println("short circuit numeric: "
                + (limit != null && limit > 0));

        int defaultLimit = limit != null ? limit : 0;
        System.out.println("default limit: " + defaultLimit);
        System.out.println("Objects.equals: " + Objects.equals(limit, 0));

        try {
            boolean active = enabled;
            System.out.println(active);
        } catch (NullPointerException e) {
            System.out.println("boolean unboxing: NullPointerException");
        }

        try {
            boolean positive = limit > 0;
            System.out.println(positive);
        } catch (NullPointerException e) {
            System.out.println("numeric comparison: NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac UnboxingConditionsDemo.java
java UnboxingConditionsDemo
```

Output:

```text
enabled == null: true
Boolean.TRUE.equals: false
short circuit boolean: false
short circuit numeric: false
default limit: 0
Objects.equals: false
boolean unboxing: NullPointerException
numeric comparison: NullPointerException
```

In both `enabled != null && enabled` and `limit != null && limit > 0`, Java stops at the left-hand side when it evaluates to false, thereby **avoiding unboxing null**. Meanwhile, `boolean active = enabled` and `limit > 0` require a primitive value, so NPE is the expected outcome per language rules.

## 9. Ternary operator `?:` and hidden unboxing

A conditional expression of the form `condition ? left : right` is a place where type conversions are very easy to overlook.

In Java, **only one of `left` or `right` is evaluated**; however, the type of the whole expression is determined by the conditional operator's typing rules at compile time. If the typing rule requires a primitive, **the chosen wrapper branch can be unboxed**.

Example:

```java
Integer maybe = null;

int safe = maybe != null ? maybe : 0; // 0; null branch is not chosen
int chosen = true ? 7 : maybe;       // 7; maybe branch is not evaluated
// int bad = false ? 7 : maybe;       // will throw NullPointerException
```

Do not rely on "this branch usually doesn't run" to skip a null policy. When conditions change at runtime, a branch holding a null wrapper can become the chosen branch.

Clearer code for potentially missing data:

```java
Integer value = null;
int effective = value == null ? 0 : value;
```

If null is a business error, rather than defaulting to 0, validate and report an explicit error before performing operations.

## 10. Wrappers with string concatenation: when `+` does not unbox

The `+` operator is both arithmetic addition and string concatenation. When **one operand is `String`**, Java concatenates the textual representation of the other operand:

```java
Integer count = null;

String message = "count=" + count; // "count=null"
```

The variable `count` remains `null`; Java simply produces the text `"null"` for concatenation. It **does not** unbox to add numbers.

The difference appears when parentheses are present:

```java
Integer a = 2;
Integer b = 3;

String first = "sum=" + a + b;     // "sum=23"
String second = "sum=" + (a + b); // "sum=5"
```

- `first`: `"sum=" + a` is already string concatenation, and `+ b` continues concatenating.
- `second`: parentheses force `a + b` to run as **numeric addition**, unboxing both wrappers to yield `int` 5; only then does string concatenation occur.

With `Integer a = null`, `"sum=" + a` produces `"sum=null"`, whereas `"sum=" + (a + 1)` throws NPE because the addition inside parentheses requires unboxing.

**Note:** do not assume concatenation with every kind of object is completely safe; a custom `toString()` written by an application can still throw an exception. For null wrappers, concatenating as `"null"` is a simple and consistent rule.

## 11. Unboxing in Collections, Streams, and aggregate APIs

Java generics require type arguments to be **reference types**. Therefore you use `List<Integer>`, not `List<int>`:

```java
java.util.List<Integer> values = java.util.Arrays.asList(1, 2, 3);
int sum = 0;

for (Integer value : values) {
    sum += value; // unbox Integer -> int
}
```

A list can contain `null` if the API permits it, in which case the addition in the loop throws NPE. The same happens in APIs expecting primitives:

```java
// values.stream().mapToInt(Integer::intValue).sum()
```

`Integer::intValue` must be called on each element; if there is a null element, the call hits NPE. You can **filter out nulls** before converting:

```java
int sum = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
```

This implicitly applies a "skip null elements" policy. If null indicates corrupted data or must be recorded, replace silent filtering with explicit validation.

### Runnable example with a list containing null

Create the file `UnboxingCollectionDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class UnboxingCollectionDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, null, 3);

        int filteredSum = values.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("filtered sum: " + filteredSum);

        try {
            int rawSum = values.stream()
                    .mapToInt(Integer::intValue)
                    .sum();
            System.out.println(rawSum);
        } catch (NullPointerException e) {
            System.out.println("raw stream: NullPointerException");
        }
    }
}
```

Run:

```bash
javac UnboxingCollectionDemo.java
java UnboxingCollectionDemo
```

Output:

```text
filtered sum: 4
raw stream: NullPointerException
```

This is an example of the **actual behavior of null values in a pipeline**; it does not mean `Stream<Integer>` automatically removes nulls or defaults them to 0.

## 12. Unboxing does not protect against overflow or division by zero

After unboxing, primitive operations follow normal rules:

```java
Integer max = Integer.MAX_VALUE;
int overflowed = max + 1; // Integer.MIN_VALUE

Integer numerator = 10;
Integer denominator = 0;
// int q = numerator / denominator; // ArithmeticException: / by zero
```

In the addition line, the result still overflows within the `int` range. In division, wrappers are unboxed to integers first; division by zero throws `ArithmeticException`, which is **not** a boxing/unboxing error.

If the data model allows null, three cases must be distinguished:

1. **Null wrapper** when unboxing is needed → `NullPointerException`.
2. **Zero divisor** after unboxing → `ArithmeticException` for integer division.
3. **Out-of-range value** in normal integer addition/subtraction/multiplication → normally does not throw an exception automatically and wraps according to integer width.

When overflow is a business error, choose checked APIs like `Math.addExact` and `Math.multiplyExact`; they still do not replace null checks if the inputs are wrappers.

## 13. Designing null-safe APIs with nullable wrappers

Before processing, explicitly decide **what null means**:

- **Number is required:** check for null and report an error with a helpful message before unboxing.
- **Null means "default 0":** convert to primitive 0 using a checked expression.
- **Null means "unknown":** preserve the missing state and handle it separately rather than turning it into 0.
- **A sequence allows skipping null values:** filter nulls intentionally, while ensuring that matches requirements.

Example method requiring a value:

```java
static int requireQuantity(Integer quantity) {
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return quantity; // safe unboxing after check
}
```

And example defaulting to 0:

```java
static int quantityOrZero(Integer quantity) {
    return quantity == null ? 0 : quantity;
}
```

The snippets above are **illustrative methods**, which need to be placed inside a class to form standalone runnable code. Choose the method based on the API contract rather than defaulting to 0 everywhere: missing data and actual zero values can carry different meanings.

With nullable `Boolean`, writing `Boolean.TRUE.equals(flag)` is especially readable when the policy is **only the true state counts as enabled**. If three states (true/false/unknown) are needed, keep `Boolean` or use an explicit domain type instead of forcing everything into a primitive.

### Use `Objects.requireNonNull` when null is an error

`java.util.Objects.requireNonNull(quantity, "quantity is required")` can validate non-null at the API boundary and throw NPE with a clear message. After the check, unboxing from the wrapper is confirmed valid.

Methods like `Objects.equals(a, b)` serve **null-safe object equality**, not automatically converting null wrappers into 0.

## 14. Performance and clarity

Autoboxing and unboxing keep Java code concise, but each conversion can involve object operations, null checks, or memory/allocation depending on context and JVM optimizations.

For heavy calculation loops, `int`, `long`, and primitive arrays are usually suitable when nullability or generics are unnecessary:

```java
long total = 0;
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    total += number;
}
```

This does not mean replacing every `List<Integer>` with a primitive array. Choose types for correctness and API constraints; evaluate performance when an actual issue is measured.

A common design mistake is using nullable wrappers in business code **without defining a null policy**. The system may work fine in normal cases, then throw NPE upon receiving missing values from a database, JSON, or API call. Checking null at data boundaries keeps errors localized and easier to trace.

## 15. Common misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| `Integer + Integer` returns `Integer` | Unboxes then performs `int` addition; expression type is `int` | Identify the operator's type; boxing happens afterward only if needed |
| `Integer null + 1` treats null as 0 | Unboxing null throws NPE | Check/define null handling before adding |
| Assigning to `Integer` prevents overflow | `int` addition can still overflow | Use wide types or `Math.*Exact` when appropriate |
| `Integer a == Integer b` always compares values | With two wrappers of the same type, `==` compares references | Use `equals` or `Objects.equals` |
| `Integer a == 0` is always safe | Wrapper is unboxed; null causes NPE | Check null before numeric comparison |
| `a == null` also unboxes | Comparing against null is a reference comparison | Safe to use for detecting missing data |
| Using `Boolean flag` in `if` needs no check | `if` requires primitive boolean, causing unboxing | Use null-check or `Boolean.TRUE.equals` |
| `"value=" + nullable` always unboxes | This is string concatenation and can display `null` | Distinguish string concatenation from numeric addition |
| `List<Integer>` cannot contain null | Lists can contain null depending on API | Check before adding or mapping to primitives |
| `count++` on `Integer` mutates the same object | Unboxes, computes primitive, boxes, and reassigns | Remember wrapper immutability |
| `int` → `Long` converts automatically in all steps | No combined primitive widening then boxing in this assignment | Create a `long` expression before boxing |

## 16. Self-check exercises

**Question 1.** What is the type of `Integer a = 2; Integer b = 3; a + b`?  
**Answer:** `int`. Java unboxes both wrappers and adds two primitive ints.

**Question 2.** If `Integer x = null;`, how do `x == null` and `x == 0` differ?  
**Answer:** `x == null` returns true because it compares references; `x == 0` requires unboxing and throws `NullPointerException`.

**Question 3.** Given `Integer x = null;`, what does `"x=" + x` produce?  
**Answer:** The string `"x=null"` because it is string concatenation, requiring no numeric unboxing.

**Question 4.** Given `Integer a = 2, b = 3;`: why does `"sum=" + a + b` differ from `"sum=" + (a + b)`?  
**Answer:** The first concatenates two textual representations, giving `"sum=23"`; the second computes `a + b` numerically via unboxing first, giving `"sum=5"`.

**Question 5.** Is `Short s = 2; int value = s * 4;` valid?  
**Answer:** Yes. Unboxes to `short`, promotes to `int`, and multiplies, giving 8.

**Question 6.** Is `Boolean enabled = null; if (enabled) { ... }` safe?  
**Answer:** No. The condition must unbox `Boolean` to `boolean` and throws NPE.

**Question 7.** Which is safer if null should be treated as false: `enabled != null && enabled` or `Boolean.TRUE.equals(enabled)`?  
**Answer:** Both. The first relies on short-circuiting; the second compares against the `Boolean.TRUE` object.

**Question 8.** Why is `Integer count = 1; count++;` valid while `count = null; count++;` causes NPE?  
**Answer:** `++` on a wrapper requires unboxing, adding 1, and boxing back. When count is null, the unboxing step fails.

**Question 9.** Given `List<Integer> list = Arrays.asList(1, null, 3)`, is `mapToInt(Integer::intValue)` safe?  
**Answer:** No if it encounters null; you can filter with `Objects::nonNull` if the data contract allows skipping such elements.

**Question 10.** Does `Integer max = Integer.MAX_VALUE; int result = max + 1;` throw NPE or ArithmeticException?  
**Answer:** No, because max is non-null. The `int` addition overflows and returns `Integer.MIN_VALUE`. To detect overflow, use `Math.addExact`.

**Question 11.** Given `Integer a = 10; Long b = 20L;`, what is the type of `a + b`?  
**Answer:** `long`. Both wrappers are unboxed; `int` is promoted to `long` before addition.

**Question 12.** What should you do to receive the sum of two `Integer` variables `x, y` in `Long result` without violating typing rules?  
**Answer:** Once x and y are confirmed non-null, write `Long result = (long) x + y;` to compute in `long` and then box the result to `Long`.

## 17. Conclusion and references

Unboxing is **converting a wrapper to its primitive when required by an expression context**. In addition, subtraction, multiplication, division, numeric comparisons, `boolean` conditions, or increment/decrement operations, Java can unbox without a visible cast keyword. After unboxing, **numeric promotion and primitive integer rules** continue to govern types, overflow, division by zero, and results.

Three practical principles:

1. **Check or define a null policy** before wrappers participate in primitive operations.
2. **Distinguish string concatenation from numeric addition, and reference equality from value equality**; the same syntax `+` or `==` can follow different rules.
3. **Do not confuse boxing/unboxing with arithmetic protection**; if overflow prevention is needed, still compute with appropriate types or checked operations.

Language specification references: [Java Language Specification — §5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [§5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [§15.18 Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18).