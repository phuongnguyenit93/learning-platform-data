# Unboxing in Assignment, Operations, and Method Invocations in Java

**Unboxing** is the conversion of a value from a **wrapper object** to its corresponding **primitive type**. For example, Java can implicitly convert `Integer` to `int`, `Long` to `long`, and `Double` to `double` when the context requires a primitive value.

```java
Integer boxed = 12; // Integer object
int number = boxed; // unboxing: Integer -> int

Integer a = 7, b = 5;
int sum = a + b;    // unboxing both a and b, then int addition

static int twice(int x) {
    return x * 2;
}
// twice(boxed) is callable: Integer -> int before passing the argument.
```

*Note:* `twice` above is an **illustrative method that must be placed inside a class**. A complete runnable program will be provided later in the lesson.

Unboxing is not a harmless transformation for all inputs: **unboxing a wrapper with value `null` throws `NullPointerException` at runtime**. And unboxing does not alter rules such as numeric promotion, overflow, integer division, or overload selection.

## 1. How do primitives differ from wrappers?

Java has pairs of primitives and wrappers:

| Primitive | Wrapper | Typical primitive extraction method |
| --- | --- | --- |
| `boolean` | `Boolean` | `booleanValue()` |
| `byte` | `Byte` | `byteValue()` |
| `short` | `Short` | `shortValue()` |
| `char` | `Character` | `charValue()` |
| `int` | `Integer` | `intValue()` |
| `long` | `Long` | `longValue()` |
| `float` | `Float` | `floatValue()` |
| `double` | `Double` | `doubleValue()` |

- A **primitive** holds a value of that type; for example, `int` holds a 32-bit integer value.
- A **wrapper** is a reference type; for example, `Integer` is an object containing an `int` value. A wrapper reference variable can be `null`.
- **Boxing** is the reverse direction: `int → Integer`, often occurring when assigning a primitive to a wrapper variable or inserting into a collection.
- **Unboxing** is the `Integer → int` direction, inserted automatically when Java needs a primitive.

```java
int primitive = 10;
Integer boxed = primitive; // boxing

int again = boxed;         // unboxing
```

Do not conflate a wrapper **object** with a **primitive value**. Unboxing reads the primitive value from the wrapper; if the wrapper does not refer to any object (`null`), there is no value to read.

## 2. Unboxing in assignment

A common pattern is **assigning a wrapper to the corresponding primitive variable**:

```java
Integer boxedInt = 42;
int primitiveInt = boxedInt;  // Integer -> int

Double boxedDouble = 3.5;
double primitiveDouble = boxedDouble; // Double -> double

Boolean enabled = Boolean.TRUE;
boolean flag = enabled; // Boolean -> boolean
```

These are **assignment contexts** where Java can perform an unboxing conversion. The unboxed result must obey the type rules of the target variable.

### Unboxing followed by primitive widening

Java also permits **unboxing followed by primitive widening**, such as `Integer → int → long`:

```java
Integer boxed = 12;
long wider = boxed;    // Integer -> int -> long, value 12L

Byte small = 10;
int number = small;    // Byte -> byte -> int
double real = boxed;   // Integer -> int -> double
```

However, do not infer that Java automatically performs every chain of type conversions:

```java
Integer source = 12;
// Long invalid = source; // Compile-time error: no automatic Integer -> int -> long -> Long

long widened = source;  // Valid: unboxing then primitive widening
Long target = (long) source; // Valid: cast to long, then boxing to Long
```

Converting `Integer` to `Long` is not a direct unboxing operation. If you need a `Long`, convert explicitly to `long` and then box.

### Unboxing `null` on assignment

```java
Integer count = null;
// int value = count; // Compiles, but NPE at runtime
```

The compiler does not reject code just because a wrapper **might** be null. However, at runtime when executing the primitive assignment, attempting to retrieve `intValue()` on a null reference leads to `NullPointerException`.

For values that may be missing, check and handle them explicitly according to the data contract:

```java
Integer count = null;
int safe = count == null ? 0 : count;  // Use 0 only if business rules specify it
```

This conditional expression does not evaluate the `count` branch when `count == null` is true, thus avoiding unboxing in the null case. **Do not automatically replace null with 0** if 0 is also meaningful data; you may choose to reject it, report an error, or keep the wrapper type until needed.

## 3. Unboxing in arithmetic operators

The arithmetic operators `+`, `-`, `*`, `/`, `%` operate on numeric primitive values. When operands are numeric wrappers, Java can **unbox them and then apply numeric promotion**:

```java
Integer a = 7;
Integer b = 5;

int sum = a + b;          // 12
int difference = a - b;   // 2
int product = a * b;      // 35
int quotient = a / b;     // 1, integer division
int remainder = a % b;    // 2
```

`a` and `b` remain `Integer` variables; only their values are converted to `int` in the **new expression**. The result `a + b` has type `int`, **not `Integer` just because the operands were declared as `Integer`**.

### Wrappers smaller than `int` still undergo numeric promotion

```java
Byte first = 10, second = 20;
int sum = first + second; // Byte -> byte then promoted to int
```

Operands of `byte` and `short` are normally promoted at least to `int` in binary operations. If one operand is `Long` and the other is `Integer`, after unboxing the operation uses `long`:

```java
Integer i = 2;
Long l = 3L;
long total = i + l; // int + long -> long
```

This does not mean a wrapper is automatically widened to another wrapper object; the promotion happens within the **primitive expression**.

### Unboxing does not protect against overflow or loss of fractional parts

```java
Integer a = 50_000;
Integer b = 50_000;

int wrong = a * b;          // -1794967296: int multiplication overflowed
long alsoWrong = a * b;     // Widens the already overflowed int result
long correct = (long) a * b; // 2500000000: unbox a, cast to long before multiplication

Integer seven = 7;
Integer three = 3;
int q = seven / three;       // 2, integer division truncates the fractional part
double real = (double) seven / three; // Approximately 2.3333333333333335
```

The result depends on **the primitive types after unboxing and casting**, not on whether you wrote wrappers or primitives in the initial declarations. If you need to detect overflow instead of getting a wrapped-around `int`/`long` value, consider `Math.multiplyExact` or `Math.addExact` with the appropriate overload and argument types.

## 4. Increment/decrement operators, compound assignment, and re-boxing

Statements like `++`, `--`, `+=` can put a wrapper through an **unbox → compute → re-box** cycle:

```java
Integer count = 5;
count++;     // get int 5, add 1, produce Integer value 6 to reassign
count += 2;  // get int 6, add 2, box back to Integer 8
```

Because wrappers are reference types, the statement does not directly mutate the contents of an *immutable* `Integer` object. It **reassigns the variable reference** to the boxed wrapper value.

```java
Integer counter = Integer.MAX_VALUE;
counter++; // Integer.MIN_VALUE due to int addition overflow
```

Unboxing and re-boxing **does not add overflow checking**. If `counter` is null, both `counter++` and `counter += 1` must unbox to compute and cause `NullPointerException`.

In addition, `count += 0.5` does not turn an `Integer` into a `Double`: compound assignment includes the corresponding conversions back to the primitive type of `count` before re-boxing. Do not use `+=` to “auto-promote” a wrapper.

## 5. Unboxing in comparisons: `==` requires checking both sides' types

This case causes errors more often than addition because `==` can be either **reference comparison** or **primitive value comparison** depending on operand types:

```java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

boolean references = (left == right); // Reference comparison; do not use to compare values
boolean values = left.equals(right);  // Wrapper value comparison: true

int primitive = 1000;
boolean mixed = (left == primitive);   // Unbox left, compare int: true
```

**Two `Integer` references in `left == right` do not automatically unbox** just because both are wrappers. When one side is a numeric primitive and the other is a numeric wrapper, Java applies numeric rules and can unbox the wrapper for comparison.

For the same reason:

```java
Integer missing = null;
boolean absent = (missing == null); // true: reference check, safe
// boolean isZero = (missing == 0);  // Compiles, but NPE on comparison
```

The relational operators `<`, `<=`, `>`, `>=` on numeric wrappers require numeric value comparison, so they will perform unboxing:

```java
Integer low = 3, high = 7;
boolean ordered = low < high; // true, unboxes both
```

With `null`, these ordering comparisons cause an NPE at runtime. Write `missing != null && missing > 0` to **short-circuit** and guard the unboxing on the right-hand side. Do not use `missing > 0 && missing != null` because the left-hand side already unboxes first.

## 6. Unboxing in method invocation

Java can convert a wrapper to a primitive to match a parameter type:

```java
static int twice(int value) {
    return value * 2;
}

// In another method:
Integer number = 12;
int answer = twice(number); // Integer -> int; result 24
```

The `twice` method requires `int`, so Java unboxes `number` when evaluating the argument. If `number == null`, the call cannot supply an `int` value, and argument preparation throws an NPE **before the body of `twice` runs**.

Unboxing can be combined with **primitive widening** for a wider parameter:

```java
static void acceptLong(long value) {
    System.out.println(value);
}

// Integer boxed = 12;
// acceptLong(boxed); // Integer -> int -> long
```

This is an illustrative snippet, not a standalone program. Type compatibility is checked at compile time, while reading the wrapper's value can cause an NPE at runtime.

### Overload resolution: Java does not always unbox just because a primitive overload exists

If multiple methods share the same name, Java selects an overload according to the **applicable phases of method invocation**: first calls requiring no boxing/unboxing (strict invocation), then wider conversions, and finally varargs.

Example:

```java
static String choose(int value)  { return "int"; }
static String choose(long value) { return "long"; }

Integer boxed = 12;
// choose(boxed) -> "int": requires unboxing; int overload is more specific than long
```

However, with these overloads:

```java
static String route(long value)     { return "long"; }
static String route(Integer value)  { return "Integer"; }

Integer boxed = 12;
// route(boxed) -> "Integer": passing the reference requires no unboxing
// route(7)     -> "long": widening int -> long is considered before boxing int -> Integer
```

And there is a subtle situation:

```java
static String view(Object value) { return "Object"; }
static String view(int value)    { return "int"; }

Integer boxed = 12;
// view(boxed) -> "Object": Integer -> Object is reference widening
//                so it is chosen in the strict phase before considering unboxing to int
```

**Therefore, you cannot assert that “a primitive overload always wins” or “Java always unboxes when possible”.** You must inspect the overload set alongside the applicable conversion phases. When code is hard to read, use explicit parameter types and avoid excessive overloading between primitives/wrappers if they lead to different semantics.

### Null also depends on which overload is chosen

```java
Integer missing = null;

// route(missing) can call the route(Integer) overload without unboxing.
// twice(missing) forces unboxing because the parameter is int -> NPE.
```

A null reference **does not cause an NPE simply by being passed**. The NPE appears when an expression or parameter actually requires a primitive and must unbox null.

## 7. Evaluation order and when NPE occurs

Java does not “check for null wrappers remotely” at compile time. It evaluates expressions and only unboxes when a primitive value is needed:

| Context | Unboxing needed? | If wrapper is null |
| --- | --- | --- |
| `int n = boxed;` | Yes | NPE |
| `long n = boxed;` with `boxed` as `Integer` | Yes, then widening | NPE |
| `int x = boxed + 1;` | Yes | NPE |
| `boxed > 0` | Yes | NPE |
| `boxed == 0` | Yes | NPE |
| `boxed == null` | No, reference comparison | No NPE from this comparison |
| `boxed == anotherBoxed` with two `Integer`s | No, reference comparison | No NPE just because one side is null |
| Calling `twice(boxed)` with `twice(int)` | Yes | NPE when preparing the argument |
| Calling `route(boxed)` when `route(Integer)` is chosen | No | Null can be passed normally |
| `boxed++` / `boxed += 1` | Yes and re-boxing | NPE |

Another case is a conditional expression with a primitive branch:

```java
Integer maybe = null;
boolean useBoxed = false;
int value = useBoxed ? maybe : 0; // 0, does not evaluate the maybe branch
```

If `useBoxed` is `true`, the `maybe` branch must supply an `int` value and will NPE when null. The compiler determines the expression type from both branches, but **only the chosen branch is evaluated at runtime**.

In a multi-argument call, argument expressions are evaluated in Java's evaluation order; if unboxing one argument throws NPE, the method body does not run. This is why merely placing `Objects.requireNonNull` inside a method taking `int` **cannot protect** against an NPE caused by unboxing on the caller side; the `int` parameter already had to be produced before entering the method.

## 8. Java 17+: complete verified example

Save in file `UnboxingContextsDemo.java`:

```java
public class UnboxingContextsDemo {
    static String choose(int value) { return "int"; }
    static String choose(long value) { return "long"; }

    static String route(long value) { return "long"; }
    static String route(Integer value) { return "Integer"; }

    static String view(Object value) { return "Object"; }
    static String view(int value) { return "int"; }

    static int twice(int value) { return value * 2; }

    public static void main(String[] args) {
        Integer boxed = 12;
        int assigned = boxed;
        long widened = boxed;
        System.out.println("assignment: " + assigned + ", long: " + widened);

        Integer a = 7, b = 5;
        System.out.println("sum: " + (a + b) + ", product: " + (a * b));
        System.out.println("comparison: " + (a > b));

        System.out.println("choose(boxed): " + choose(boxed));
        System.out.println("route(boxed): " + route(boxed));
        System.out.println("route(7): " + route(7));
        System.out.println("view(boxed): " + view(boxed));
        System.out.println("twice(boxed): " + twice(boxed));

        Integer counter = Integer.MAX_VALUE;
        counter++;
        System.out.println("counter after ++: " + counter);

        Integer absent = null;
        System.out.println("absent == null: " + (absent == null));
        System.out.println("route(absent): " + route(absent));

        try {
            int x = absent;
        } catch (NullPointerException ex) {
            System.out.println("assignment null: NPE");
        }
        try {
            int x = absent + 1;
        } catch (NullPointerException ex) {
            System.out.println("arithmetic null: NPE");
        }
        try {
            boolean x = absent == 0;
        } catch (NullPointerException ex) {
            System.out.println("comparison null: NPE");
        }
        try {
            twice(absent);
        } catch (NullPointerException ex) {
            System.out.println("invocation null: NPE");
        }
    }
}
```

Compile and run:

```bash
javac UnboxingContextsDemo.java
java UnboxingContextsDemo
```

Stdout:

```text
assignment: 12, long: 12
sum: 12, product: 35
comparison: true
choose(boxed): int
route(boxed): Integer
route(7): long
view(boxed): Object
twice(boxed): 24
counter after ++: -2147483648
absent == null: true
route(absent): Integer
assignment null: NPE
arithmetic null: NPE
comparison null: NPE
invocation null: NPE
```

**Reading the output:**

- Assigning `Integer` to `int` or `long` illustrates **unboxing**, and with `long` there is a widening step after unboxing.
- The operations `a + b`, `a * b`, `a > b` force extracting `int` values to compute.
- `choose`, `route`, and `view` prove that overload selection **is not based solely on “primitive vs. wrapper”**, but on the applicable conversion phases.
- `counter++` uses `int` internally, so it still overflows and boxes back.
- `absent == null` along with `route(absent)` do not require unboxing; the last four cases force unboxing and cause NPEs, which are caught individually.

## 9. Unboxing in collections and generics

Java generics use reference types for type arguments, so `List<int>` is invalid; `List<Integer>` is commonly used instead. When adding an `int`, Java boxes it; when retrieving it to compute with `int`, Java unboxes it:

```java
java.util.List<Integer> scores = new java.util.ArrayList<>();
scores.add(10);    // int -> Integer (boxing)
scores.add(20);

int sum = 0;
for (Integer score : scores) {
    sum += score;   // Integer -> int (unboxing)
}
```

If the collection contains `null`, the loop `sum += score` can throw an NPE. This does not happen merely because `scores.add(null)` was called; the error occurs when the `null` data **is used in a primitive context**.

With `Map<String, Integer>`, `map.get(key)` can return `null` if the key does not exist (or if the key is mapped to null). Code like `int n = map.get(key);` easily causes an NPE. Depending on business logic, you can check `containsKey`, use `getOrDefault` with an appropriate default, or keep `Integer` to represent an absent value.

**Performance note:** boxing/unboxing can create or access wrappers and increase overhead in large loops or multi-element data structures. However, do not optimize by eliminating all wrappers if nullability/generics are needed. When storing large quantities of data that only need primitives, `int[]` or `double[]` arrays are an option to consider.

## 10. `var` and wrappers: types may look unclear

`var` infers its type from the initializer expression, not from how it is used later:

```java
var wrapper = Integer.valueOf(5); // Integer
var primitive = wrapper + 1;       // int because of unboxing then int addition
var another = wrapper;             // Integer, keeps the static type of the expression
```

Therefore `var` does not automatically avoid NPEs: `var x = wrapper + 1` still has to unbox `wrapper` when evaluating the initializer. If `wrapper` is null, the addition throws an NPE **before `x` receives a value**.

Do not confuse a method returning `Integer` with a method returning `int` just because both print the same digits at runtime. In code handling many overloads/generics, you can write explicit types so readers know whether **the value can be null**.

## 11. How to avoid unboxing bugs and write clear APIs

### Decide whether missing data is allowed

If `null` means “unknown”, “absent”, or “not entered”, using a wrapper at the data layer may make sense. However, when moving to arithmetic operations, you must decide:

- **Reject missing data:** for example `Objects.requireNonNull(value, "value")`, then perform the operation. The NPE is then controlled with a clear message.
- **Use a default value:** only when business rules define a default, such as treating missing quantity as 0.
- **Preserve the absent-value state:** do not unbox until the appropriate processing branch or use a data model that expresses absence.

```java
Integer maybe = null;

if (maybe != null && maybe > 0) {
    System.out.println("Positive");
}
```

The `&&` operator evaluates via short-circuiting: when `maybe != null` is false, the right-hand side **does not execute**, so null is not unboxed.

### Design method signatures to reduce surprises

If a function always requires a valid integer and does not allow missing values, an `int` parameter clearly shows that contract. Yet a call passing `Integer` can still NPE due to unboxing on the caller side; validate data before calling.

If the method truly permits null, use `Integer` and handle null **inside the method**. When overloading among `int`, `long`, `Integer`, and `Object`, test resolution with primitive, wrapper, and null cases; if semantics differ too much, consider different method names or explicit casts to avoid readability issues.

### Do not use `==` between two wrappers to compare numeric content

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

// a == b: compares identity, should not be used to check numeric equality.
boolean equalValues = a.equals(b); // true
```

Choose `Objects.equals(a, b)` if both can be null and you want null to equal null; or unbox after verifying non-null to use primitive `==`. With `Float`/`Double`, `equals` has NaN and signed zero semantics that differ from primitive `==`, so determine the desired rule.

### Prefer explicit conversions if range matters

If an `Integer` participates in multiplication that risks exceeding 32 bits, unbox and promote one operand to `long` **before multiplication**, such as `(long) a * b`; when overflow checking is needed, use `Math.multiplyExact` with the matching `long` overload. Do not assume boxing/unboxing has built-in overflow detection.

## 12. Common misconceptions

1. **“A wrapper is just a nullable primitive; Java always unboxes it as soon as it is created.”** False: unboxing happens when the context requires a primitive value, not as soon as a wrapper reference appears.
2. **“`Integer a = null; int b = a;` does not compile.”** False: it compiles, but unboxing `null` causes an NPE at runtime.
3. **“`Integer + Integer` always creates a new `Integer`.”** False: arithmetic operators unbox operands and apply numeric promotion; the result has a primitive type unless boxed afterward in an appropriate assignment/return context.
4. **“`Integer * Integer` is safe from overflow.”** False: after unboxing it is still `int` multiplication if both sides are `Integer`.
5. **“`Integer a = null; a == null` throws NPE.”** False: this is a safe reference comparison; `a == 0` is what requires unboxing.
6. **“`a == b` with two `Integer`s always compares numeric values.”** False: it normally compares references and does not automatically unbox both sides.
7. **“A primitive overload always beats a wrapper overload.”** False: the `route(Integer)` overload is chosen for a matching `Integer` argument without unboxing.
8. **“A primitive overload always beats `Object` if the argument is `Integer`.”** False: reference widening to `Object` can be considered in the strict phase before unboxing.
9. **“Passing a `null` reference to any method causes an NPE.”** False: only when argument preparation or the method body needs a primitive or performs an unsafe dereference.
10. **“`counter++` on an `Integer` mutates the existing object.”** False: wrappers are immutable; the operation unboxes, boxes, and reassigns the variable.
11. **“`Long target = integerWrapper` is valid because `long x = integerWrapper` is valid.”** False: `Integer → int → long` can go into a primitive `long`, but does not automatically chain another boxing step to `Long` in that assignment.
12. **“`List<Integer>` guarantees no `null` elements, so extracting to `int` is always safe.”** False: a list can contain null; unboxing on assignment/computation will throw NPE.

## 13. Self-check

**1. `Integer x = 8; int y = x;` — what happens?** → Unboxing `Integer → int` on assignment; `y` equals 8.

**2. Is `Integer x = 8; long y = x;` valid?** → Yes: unboxes to `int` then widens to `long`.

**3. `Integer a = 5, b = 6;` — what is the type of `a + b`?** → `int`, not `Integer`.

**4. `Integer n = null;` — which expression is safer to check for null: `n == null` or `n == 0`?** → `n == null`; the other expression requires unboxing and causes an NPE.

**5. If both `route(long)` and `route(Integer)` exist, which version does `route(7)` call?** → `route(long)` because primitive widening `int → long` is considered before boxing `int → Integer`. Meanwhile, `route(Integer.valueOf(7))` selects `route(Integer)`.

**6. If `view(Object)` and `view(int)` coexist, which overload is chosen when passing `Integer`?** → `view(Object)` via reference widening in the strict phase before considering unboxing.

**7. `Integer counter = Integer.MAX_VALUE; counter++;` — what does it yield?** → `Integer.MIN_VALUE` because primitive `int` addition overflows, and then it boxes back.

**8. In `int v = map.get(key);` with `Map<String,Integer>`, what risk needs checking?** → `get` can return null, and unboxing during assignment to `int` causes an NPE.

**Key takeaway:** Unboxing **converts a wrapper to a primitive when the context requires a value**, commonly seen in **assignments**, **arithmetic/comparison operators**, and **method arguments**. Java can combine unboxing with primitive widening and re-box after an operation, but it **does not automatically convert any wrapper to another wrapper**. Expression types, selected overloads, and `NullPointerException` risks must be evaluated according to the **specific context**, not by the fact that two variables print the same number.
