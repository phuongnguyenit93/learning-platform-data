# Boxing, Unboxing, and Autoboxing in Java 17+

## 1. What Are Boxing and Unboxing?

Java has **primitive types** (*primitives*) such as `int`, `long`, `double`, `boolean`, and corresponding **wrapper classes** such as `Integer`, `Long`, `Double`, `Boolean`.

- **Boxing**: converts **a primitive value into the corresponding wrapper object**, such as `int → Integer`.
- **Unboxing**: extracts **the primitive value from a wrapper**, such as `Integer → int`.
- **Autoboxing / auto-unboxing**: the compiler accepts these conversions **implicitly** in contexts permitted by Java, without requiring you to call a conversion method manually.

~~~java
int primitive = 42;
Integer boxed = primitive; // Autoboxing: int -> Integer
int restored = boxed;      // Auto-unboxing: Integer -> int

System.out.println(boxed);    // 42
System.out.println(restored); // 42
~~~

This can be visualized as:

~~~mermaid
flowchart LR
    A["int: 42"] -->|"boxing"| B["Integer holding value 42"]
    B -->|"unboxing"| C["int: 42"]
~~~

**Important:** a wrapper is a **reference object**, not a second primitive type. Both can represent the same number, but they differ in their ability to hold `null`, APIs, object identity, and usage overhead.

## 2. Which Type Pairs Are Boxed and Conversion Limits

The eight primitive → wrapper pairs in Java 17 are **`byte/Byte`, `short/Short`, `int/Integer`, `long/Long`, `float/Float`, `double/Double`, `char/Character`, `boolean/Boolean`**. `void` has no value to box; the `Void` class serves certain specialized APIs.

~~~java
Integer quantity = 7; // int -> Integer.
Long size = 7L;       // long -> Long.
// Long invalid = 7; // Invalid: does not chain int -> long -> Long on assignment.
~~~

Note that the compiler only applies **conversions permitted by the language in each specific context**; it does not automatically turn an arbitrary primitive into an arbitrary wrapper. After boxing, the variable holds a reference and can be assigned `null`; a primitive cannot.


## 3. Explicit Boxing and Autoboxing

Two ways to create an `Integer` value from an `int`:

~~~java
int value = 12;

Integer automatic = value;          // Autoboxing
Integer explicit = Integer.valueOf(value); // Explicit factory call
~~~

Both variables have type `Integer`. When you need a wrapper and want the code to clearly express intent, `Integer.valueOf(int)` is a useful API. **There is no need** to use the `new Integer(value)` constructor: numeric wrapper constructors of this form have been deprecated and marked for removal; using `valueOf` is preferred.

~~~java
Boolean flag = Boolean.valueOf(true);
Double reading = Double.valueOf(2.5);
Character letter = Character.valueOf('A');
~~~

**Do not assume from boxing that a new object is guaranteed to be allocated every time.** Java and the wrapper classes may use cached objects, or the compiler/JVM may optimize; what matters for the application is **value and semantics**, not counting object allocations by eye.

## 4. Explicit and Automatic Unboxing

~~~java
Integer boxed = Integer.valueOf(15);

int automatic = boxed;       // Auto-unboxing
int explicit = boxed.intValue(); // Method to get primitive

System.out.println(automatic); // 15
System.out.println(explicit);  // 15
~~~

Wrappers define corresponding methods such as `longValue()`, `doubleValue()`, `booleanValue()`, `charValue()`, etc.

**Note:** `Number.intValue()` and numeric conversion methods on other wrappers can combine both **unboxing and a numeric type conversion**, depending on the class. Do not assume `doubleValue()` or `intValue()` preserves all information of a large value or one with a fractional part.

In ordinary arithmetic operations, wrappers are **unboxed** to participate in computation:

~~~java
Integer one = 10;
Integer two = 20;

int total = one + two;
System.out.println(total); // 30
~~~

Here `one + two` has type `int`, not an addition of two "Integer objects" via operator overloading.

## 5. Biggest Risk: A Wrapper Can Be Null

A primitive `int` **cannot hold `null`**, whereas an `Integer` variable can:

~~~java
Integer missing = null;
System.out.println(missing == null); // true
~~~

Attempting to auto-unbox `missing` causes **`NullPointerException` at runtime**:

~~~java
Integer missing = null;

try {
    int count = missing; // Valid compile; runtime unboxes null
    System.out.println(count);
} catch (NullPointerException ex) {
    System.out.println("unboxing null failed");
}
~~~

Output:

~~~text
unboxing null failed
~~~

Some similar traps:

~~~java
Integer quantity = null;
// int next = quantity + 1; // Unboxing null -> NullPointerException

Boolean permitted = null;
// if (permitted) { ... }    // Auto-unboxing null -> NullPointerException
~~~

**Safe practices:**

- If data **must not be missing**, use a primitive or check for null at the input boundary.
- If data may be **absent**, use a wrapper along with an explicit null-handling policy.
- When you only need to check for null, write `boxed == null` **without unboxing**.
- Do not overuse a default value of `0` to mask an input that is genuinely missing.

Example of a default policy:

~~~java
Integer maybeCount = null;
int count = maybeCount != null ? maybeCount : 0;
System.out.println(count); // 0
~~~

This is an **intentional business decision**, not Java's default behavior. Avoid defaulting to 0 if 0 and "not entered" are two different states.

## 6. Where Unboxing Changes How `==` Is Interpreted

~~~java
Integer first = Integer.valueOf(1000);
Integer sameValue = Integer.valueOf(1000);
int primitive = 1000;

System.out.println(first.equals(sameValue)); // true: compares values.
System.out.println(first == primitive);      // true: unboxes, compares int.
~~~

**`Integer == Integer`** compares references; **`Integer == int`** unboxes and compares numbers, which can throw an NPE if the wrapper is null. For two wrappers that may be null, `Objects.equals(a, b)` usually matches the goal of comparing values; for wrappers of different types, `Integer.valueOf(5).equals(Long.valueOf(5L))` is still false.

Wrapper caching makes `==` on small numbers sometimes return true; do not rely on it to check numeric equality. Details about `NaN`, signed zero, caching, and comparison contracts belong to the next two lessons on equality and caching. What matters here is knowing **which operations force unboxing**, without conflating the different `==` cases.


## 7. Wrappers Are Immutable: `Integer++` Does Not Modify the Object

Standard wrapper classes such as `Integer`, `Double`, and `Boolean` are **immutable**: there is no operation that changes the primitive value inside an already created instance.

~~~java
Integer count = 5;
Integer before = count;

count++;

System.out.println(count);  // 6
System.out.println(before); // 5
~~~

Behaviorally, the meaning of `count++` is:

1. Unbox `count` from `Integer` to `int`.
2. Add 1 according to `int` arithmetic rules.
3. Box the result into an `Integer`.
4. Assign the resulting reference value back to the variable `count`.

This does **not** modify the instance that the variable `before` still references.

~~~java
final Integer limit = 5;
// limit++; // Compile error: attempts to reassign a final variable
~~~

Use `int` for continuous counting/arithmetic when you do not need null or a reference-type API, helping avoid unnecessary boxing/unboxing.

## 8. Boxing in Method Calls and Overloading

The compiler applies argument type adaptation rules in the **method invocation context**. For example:

~~~java
static void acceptInteger(Integer value) {
    System.out.println("Integer=" + value);
}

// In main:
acceptInteger(7); // Autoboxing int -> Integer
~~~

In this example `acceptInteger(7)` is valid because the method expects `Integer` and the argument is `int`.

An easily confused overload:

~~~java
static void choose(long value) {
    System.out.println("long");
}

static void choose(Integer value) {
    System.out.println("Integer");
}
~~~

Calling:

~~~java
choose(7);                   // Prints long
choose(Integer.valueOf(7));  // Prints Integer
~~~

When the argument is `int`, primitive widening from `int` to `long` is considered in the matching phase before boxing. When the argument is already `Integer`, the overload taking exact `Integer` is the best match in this example.

There is no blanket rule that "primitive is always preferred over wrapper": Java evaluates **all overloads and argument types**, including strict/loose invocation, subtyping, boxing/unboxing, varargs, and specificity between methods.

### An INVALID Conversion

~~~java
static void acceptLongBox(Long value) {}

// acceptLongBox(7);  // Does not compile: int does not widen then box to Long
acceptLongBox(7L);    // Compiles: long -> Long via boxing
~~~

A good study habit is to always ask: **what is the type of the passed-in expression?** The literal `7` defaults to `int`, while `7L` is `long`.

## 9. Boxing, Unboxing, and Numeric Promotion in Expressions

In arithmetic, wrappers are typically unboxed and then subjected to Java's numeric promotion:

~~~java
Byte small = (byte) 100;
Short additional = (short) 20;

int result = small + additional; // byte/short -> int
System.out.println(result); // 120
~~~

`small + additional` does **not** produce a result of type `Byte` or `Short`: Java unboxes and promotes the numeric types to `int`.

~~~java
Integer count = 10;
long wider = count; // Integer -> int (unboxing) -> long (widening)
System.out.println(wider); // 10
~~~

This is valid; conversely, Java does not allow every reversed widening-and-boxing chain such as `Long n = 10;`.

Note that if an arithmetic result overflows **before** boxing, assigning to a wider wrapper will not save the result:

~~~java
Integer max = Integer.MAX_VALUE;
long wrong = max + 1;         // int overflows first
long correct = (long) max + 1; // Unbox/cast to long first

System.out.println(wrong);   // -2147483648
System.out.println(correct); // 2147483648
~~~

When writing calculations, check **the types of the operands at the time of addition**, not just the type of the receiving variable.

## 10. Boxing/Unboxing at Collection Boundaries

In Java 17, generics require reference types: `List<Integer>` is valid, while `List<int>` is invalid. Observe the exact **points of type conversion**:

~~~java
java.util.List<Integer> numbers = new java.util.ArrayList<>();
numbers.add(2); // int -> Integer on add
numbers.add(3);

int sum = 0;
for (int n : numbers) { // Integer -> int when reading each element
    sum += n;
}
System.out.println(sum); // 5
~~~

If the collection contains a `null` element, a loop using an `int` variable can throw `NullPointerException` right when retrieving the element. `List.of(...)` forbids null elements, while some other collections may allow them. Verify the null contract before relying on unboxing.

## 11. Parsing Is a Different Operation from Boxing

~~~java
int parsed = Integer.parseInt("42");       // String -> int via parsing
Integer wrapped = Integer.valueOf("42");   // String -> Integer via factory
Integer boxedParsed = Integer.parseInt("42"); // Parsing then boxing
~~~

Java does not automatically parse a `String` just because the target is a wrapper (`Integer n = "42";` does not compile). Invalid strings can cause `NumberFormatException`; subsequent parsing lessons explain radix, return types, and validation.

## 12. Boxing Does Not Erase Floating-Point Characteristics

~~~java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN))); // true
~~~

`Double.equals` also distinguishes `+0.0` and `-0.0`, unlike `==` between two `double` values. This is **the wrapper's equality rule**, not an incorrect boxing conversion. The wrapper comparison lesson goes deeper into NaN, signed zero, and caching.

## 13. When to Avoid Unnecessary Conversions?

A calculation on data that is always present should usually use primitives to keep code clear and reduce unnecessary boxing/unboxing. When APIs/generics require references or `null` has business meaning, wrappers are appropriate, but unboxing sites must be guarded. Do not conclude that every boxing operation definitely allocates an object, and do not choose types solely based on performance guesses; analyze requirements first and measure performance later if needed.

## 14. Complete Java 17 Program — Run and Verify

Create the exact file **`BoxingUnboxingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class BoxingUnboxingDemo {
    private BoxingUnboxingDemo() {}

    static void choose(long value) {
        System.out.println("choose=long");
    }

    static void choose(Integer value) {
        System.out.println("choose=Integer");
    }

    static void acceptLongBox(Long value) {
        System.out.println("Long wrapper=" + value);
    }

    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;
        int restored = boxed;
        System.out.println("boxed=" + boxed);
        System.out.println("unboxed=" + restored);
        System.out.println("explicit=" + boxed.intValue());

        Boolean flag = true;
        Character letter = 'A';
        System.out.println("wrappers=" + flag + "," + letter);

        Integer first = Integer.valueOf(1000);
        Integer alias = first;
        Integer sameValue = Integer.valueOf(1000);
        System.out.println("identity alias=" + (first == alias));
        System.out.println("equal values=" + first.equals(sameValue));
        System.out.println("boxed vs primitive=" + (first == 1000));

        Integer counter = 5;
        Integer snapshot = counter;
        counter++;
        System.out.println("incremented=" + counter);
        System.out.println("snapshot=" + snapshot);

        Integer missing = null;
        System.out.println("missing=" + (missing == null));
        System.out.println("null-safe equals="
                + Objects.equals(missing, Integer.valueOf(5)));
        try {
            int failed = missing;
            System.out.println(failed);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null=NullPointerException");
        }

        Integer boxedInt = 10;
        long widened = boxedInt;
        System.out.println("unbox widen=" + widened);

        choose(7);
        choose(Integer.valueOf(7));
        acceptLongBox(7L);

        List<Integer> values = new ArrayList<>();
        values.add(2);
        values.add(3);
        int total = 0;
        for (int value : values) {
            total += value;
        }
        System.out.println("list=" + values);
        System.out.println("list sum=" + total);

        Integer a = Integer.valueOf("42");
        int b = Integer.parseInt("42");
        System.out.println("parsed wrappers=" + a + "," + b);

        Integer number = Integer.valueOf(5);
        Long bigger = Long.valueOf(5L);
        System.out.println("different wrapper classes="
                + number.equals(bigger));

        Double nan1 = Double.valueOf(Double.NaN);
        Double nan2 = Double.valueOf(Double.NaN);
        Double plusZero = Double.valueOf(0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("boxed NaN equals=" + nan1.equals(nan2));
        System.out.println("boxed zero equals="
                + plusZero.equals(minusZero));
        System.out.println("primitive zero equals=" + (0.0 == -0.0));
    }
}
~~~

**Requirements:** JDK 17+ installed, terminal in the directory containing the source file. No Maven, Gradle, or libraries outside the JDK are needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BoxingUnboxingDemo.java
java -cp . BoxingUnboxingDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BoxingUnboxingDemo.java
java -cp . BoxingUnboxingDemo
~~~

**Exact expected output:**

~~~text
boxed=42
unboxed=42
explicit=42
wrappers=true,A
identity alias=true
equal values=true
boxed vs primitive=true
incremented=6
snapshot=5
missing=true
null-safe equals=false
unboxing null=NullPointerException
unbox widen=10
choose=long
choose=Integer
Long wrapper=7
list=[2, 3]
list sum=5
parsed wrappers=42,42
different wrapper classes=false
boxed NaN equals=true
boxed zero equals=false
primitive zero equals=true
~~~

**Points to observe:**

1. `Integer boxed = primitive` and `int restored = boxed` demonstrate autoboxing/unboxing.
2. `first == alias` is true because both variables hold the same reference; `first.equals(sameValue)` is true because they are equal by **value**. Do not rely on wrapper caching to predict the identity of `first` and `sameValue`.
3. `Integer counter++` creates a new result after unboxing/adding/boxing; `snapshot` keeps the value 5.
4. Unboxing `missing` causes `NullPointerException`, which is caught so the program continues.
5. `choose(7)` selects the `long` overload, while `choose(Integer.valueOf(7))` selects the `Integer` overload.
6. `List<Integer>` receives primitive numbers via boxing, and the loop using `int` extracts values via unboxing.
7. `Double.equals` compares NaN and signed zero differently from primitive `==`.

## 15. Common Mistakes and How to Fix Them

| Mistake / Misconception | Why Is It Wrong? | How to Handle It |
|---|---|---|
| `Integer` and `int` are completely equivalent | One is a nullable reference, the other is a primitive | Choose based on the data/API contract |
| `int value = nullableInteger;` is always safe | Unboxing null causes `NullPointerException` | Check for null or design as a required primitive |
| `if (Boolean.TRUE.equals(flag))` and `if (flag)` are always the same | `flag = null` makes the latter fail | Use a clear null policy |
| `Integer a == Integer b` to compare numbers | Compares identity; results are skewed by caching | Use `equals`/`Objects.equals` |
| `Integer a == int b` compares object identity | One primitive operand triggers unboxing | Use only when the wrapper is guaranteed non-null |
| `Integer a = 5; a++` modifies the old object | Wrappers are immutable | Variable `a` is assigned a reference to the new result |
| `Long n = 7;` | Does not automatically chain int -> long -> Long | Write `Long n = 7L;` |
| `List<int>` in Java 17 | Generics do not accept primitive type arguments | Use `List<Integer>` |
| Loop `for (int n : values)` with null Integer elements | Unboxing null immediately during iteration | Validate data / handle nullable elements |
| Using wrappers in heavy loops without measuring | Boxing can increase object and GC overhead | Consider primitives, arrays, and benchmarking |
| `Integer n = "42";` | String does not automatically convert to wrapper | `Integer.valueOf("42")` |
| `Integer.valueOf(5).equals(Long.valueOf(5L))` returns true | `Integer`'s `equals` does not convert wrapper types | Choose an appropriate numeric conversion if comparing numbers of different types |
| `Double.equals` is completely identical to floating-point `==` | NaN and signed zero have different rules | Clearly define equality semantics |

### What Boxing Does NOT Do

Boxing **does not**:

- Automatically turn a `String` into a numeric type.
- Guarantee that every boxing operation allocates a new object.
- Prevent overflow bugs in primitive addition.
- Allow automatic passing/assignment through arbitrary chains of widening, narrowing, and boxing.
- Eliminate the possibility of `NullPointerException` when unboxing a wrapper.
- Cause `==` on two wrappers to automatically become a content comparison.

## 16. Exercises with Answers

### Exercise A — Identifying Boxing and Unboxing

~~~java
int n = 10;
Integer wrapped = n;
int back = wrapped;
System.out.println(back);
~~~

**Answer:** prints `10`. The assignment `n → wrapped` is autoboxing; `wrapped → back` is unboxing.

### Exercise B — Nullable Wrapper

~~~java
Integer value = null;
// int n = value;
System.out.println(value == null);
~~~

**Answer:** prints `true`; if the commented line is executed, a `NullPointerException` will occur during unboxing. Compilation can still succeed when that line is uncommented, because the error happens at runtime.

### Exercise C — Incrementing a Wrapper Variable by One

~~~java
Integer a = 3;
Integer b = a;
a++;
System.out.println(a);
System.out.println(b);
~~~

**Answer:**

~~~text
4
3
~~~

Wrappers are immutable, so `a++` does not modify the value of the object that `b` points to.

### Exercise D — Same Number, Different Wrappers

~~~java
Integer n = Integer.valueOf(5);
Long l = Long.valueOf(5L);
System.out.println(n.equals(l));
~~~

**Answer:** `false`. `Integer.equals` does not compare numerically across different wrapper types.

### Exercise E — Overloading

~~~java
static void f(long n) { System.out.println("long"); }
static void f(Integer n) { System.out.println("Integer"); }

// In main:
f(7);
f(Integer.valueOf(7));
~~~

**Answer:**

~~~text
long
Integer
~~~

### Exercise F — Wrapper Collection

~~~java
java.util.List<Integer> nums = java.util.List.of(2, 3);
int sum = 0;
for (int n : nums) {
    sum += n;
}
System.out.println(sum);
~~~

**Answer:** `5`. The `Integer` elements are unboxed when assigned to the `int` loop variable.

## 17. Summary Checklist

- [ ] Clearly distinguish primitive `int` from wrapper `Integer`.
- [ ] Know that boxing/autoboxing converts a primitive to a wrapper, and unboxing extracts the primitive.
- [ ] List all eight primitive–wrapper pairs that hold values.
- [ ] Understand that wrappers can be `null`, whereas the corresponding primitives cannot.
- [ ] Never unbox a null wrapper in arithmetic, `if`, primitive comparisons, or loops.
- [ ] Use `equals` or `Objects.equals` when you want to compare **wrapper values**.
- [ ] Know that `==` between two wrappers compares **identity**, while a wrapper with a primitive can trigger unboxing.
- [ ] Understand that caching makes `==` on two wrappers unreliable for comparing values.
- [ ] Understand that `Integer++` is unbox → compute → box → reassign; wrappers are immutable.
- [ ] Grasp the impact of boxing/unboxing on overloading and numeric promotion.
- [ ] Know that `Long n = 7;` is not equivalent to `Long n = 7L;`.
- [ ] Know why generics like `List<Integer>` use wrappers.
- [ ] Distinguish `parseInt` from `valueOf`.
- [ ] Remember the differences between `Double.equals` and primitive `==` for NaN and signed zero.
- [ ] Compile/run `BoxingUnboxingDemo.java` with Java 17+ `javac`/`java` and verify all output.

**Conclusion:** **Boxing** turns a primitive value into a wrapper; **unboxing** retrieves the primitive; **autoboxing** lets Java perform that conversion implicitly in well-defined contexts. This convenience must be paired with discipline around `null` handling, comparisons, overloading, precision, and performance cost. Prefer primitives for calculations that must always have a value, and use wrappers when APIs/generics or potentially absent data truly require them.