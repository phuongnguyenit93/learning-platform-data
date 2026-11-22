# Objects.equals and Handling Nullable Wrappers in Java

In Java, wrapper types such as `Integer`, `Long`, `Double`, and `Boolean` are **reference types**, so wrapper variables can hold `null`. Even though autoboxing/unboxing makes many expressions look like they work with primitives, **unboxing a null reference throws `NullPointerException`**. On the other hand, calling `a.equals(b)` also throws an exception if `a == null`.

`java.util.Objects.equals(a, b)` is the standard tool for comparing two objects **without calling `equals` on a potentially null reference**. However, it does **not** automatically convert `Integer` to `Long`, does **not** unbox for numeric comparison, and does **not** replace a missing-data handling policy. This lesson presents the mechanism, corner cases, and how to write safe Java 17+ code.

## 1. How do nullable wrappers differ from primitives?

~~~java
int primitive = 0;          // Always has an int value
Integer wrapper = null;     // Can be null
Integer boxed = 0;          // Autoboxing: int -> Integer
int unboxed = boxed;        // Unboxing: Integer -> int
~~~

The wrappers `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `Character`, and `Boolean` are reference classes. They can represent a **concrete value** or **no object** (`null`). `null` is not synonymous with zero, `false`, or NaN.

| State | Example | Meaning |
| --- | --- | --- |
| Primitive `int` | `0` | Has integer value 0 |
| Wrapper `Integer` | `Integer.valueOf(0)` | Has an object containing value 0 |
| Wrapper `Integer` | `null` | No object from which to retrieve a value |
| Primitive `double` | `Double.NaN` | Has a special `double` value; **not null** |

A null wrapper can arise from an optional data field, a missing cell in external data, an API return value, or a collection element. If business requirements distinguish “unknown” from “equals 0”, using a nullable wrapper may fit; if a field is always required, primitives or non-null validation typically eliminate an error state.

## 2. Three comparison approaches and null-safety levels

### Approach 1 — `a.equals(b)`

~~~java
Integer a = null;
Integer b = 5;

// a.equals(b); // NullPointerException: a is null
~~~

When `a` is non-null, calling `a.equals(b)` returns a boolean according to the object's equality contract. However, if `a` might be null, you must check first.

### Approach 2 — `Objects.equals(a, b)`

~~~java
import java.util.Objects;

Integer a = null;
Integer b = 5;

boolean first = Objects.equals(a, b);      // false
boolean second = Objects.equals(a, null);  // true
boolean third = Objects.equals(null, null); // true
~~~

`Objects.equals` defines equivalent logic:

~~~java
static boolean equivalentToObjectsEquals(Object a, Object b) {
    return a == b || (a != null && a.equals(b));
}
~~~

This is an **illustrative method**, not a replacement for the Java library definition. The branches mean:

- Both arguments null → `true`, because both are the null reference.
- One null, one non-null → `false`.
- Two objects sharing the same reference → `true`.
- Two objects with different references and `a` non-null → calls `a.equals(b)`.

The phrase “null-safe” means the utility **does not call an instance method on a first argument that is null**. It does not mean it can mask every bug in a developer's custom `equals`, or turn null data into a numeric value.

### Approach 3 — the `==` operator

`==` has **two semantics** depending on the static types of its operands:

~~~java
Integer x = Integer.valueOf(5);
Integer y = Integer.valueOf(5);
int five = 5;

boolean numberComparison = (x == five);  // true, unboxes x
boolean referenceComparison = (x == y);  // checks for same reference
~~~

In `x == five`, Java unboxes `Integer` to `int` and compares primitives; if `x` is null, it can throw `NullPointerException`. In `x == y` when **both operands are `Integer` references**, Java compares object references. The result can depend on object caching; do not use `==` to express value equality between wrappers. Notable exception: `x == null` is a reference comparison, **does not unbox `x`**, and is safe.

## 3. `Objects.equals` does not auto-unbox or promote types

Numeric wrappers implement `equals` per concrete class. Therefore:

~~~java
Integer count = Integer.valueOf(10);
Long total = Long.valueOf(10L);

boolean sameInteger = Objects.equals(count, Integer.valueOf(10)); // true
boolean differentWrappers = Objects.equals(count, total);         // false
boolean literalsWithDifferentTypes = Objects.equals(10, 10L);     // false
~~~

On the last line, Java boxes the arguments `10` to `Integer` and `10L` to `Long` when passing them to a method accepting `Object`; `Objects.equals` does not perform the arithmetic comparison `10 == 10L`.

Quick comparison:

| Expression | Result | Why? |
| --- | --- | --- |
| `Objects.equals(null, null)` | `true` | Both references are null |
| `Objects.equals(null, 10)` | `false` | Only one side is null |
| `Objects.equals(10, 10)` | `true` | Same `Integer` wrapper, same value |
| `Objects.equals(10, 10L)` | `false` | `Integer` differs from `Long` |
| `10 == 10L` | `true` | Primitive numeric promotion |
| `Objects.equals(Double.NaN, Double.NaN)` | `true` | `Double.equals` treats two NaNs as equal |
| `Objects.equals(+0.0, -0.0)` | `false` | `Double.equals` distinguishes signed zeros |

**You should not use `Objects.equals` to compare numeric values across different wrapper types.** If `Integer(10)` and `Long(10)` need to be treated as the same number, define the numeric range and type-conversion rules. For example, when both arguments are guaranteed to be non-null integer wrappers within the `long` range, you can use `a.longValue() == b.longValue()`. Do not blindly convert every `Number` to `doubleValue()`: large integers can lose precision.

## 4. Unboxing null: errors do not vanish thanks to autoboxing

This example **intentionally throws at runtime** if uncommented:

~~~java
Integer count = null;

// int primitive = count;   // NullPointerException: unboxing
// int next = count + 1;    // NullPointerException: + operator must unbox
// boolean positive = count > 0; // NullPointerException
// boolean zero = (count == 0);  // NullPointerException
~~~

Even though `count` has a wrapper type, arithmetic operators or comparisons with primitives must extract the `int` value from the object. When the object is null, unboxing cannot proceed.

Conversely:

~~~java
Integer count = null;
boolean isAbsent = (count == null); // true, no unboxing
boolean same = Objects.equals(count, null); // true, no unboxing
~~~

The distinction between `count == null` and `count == 0` is critical. The first checks whether an object exists; the second attempts to extract a numeric value from the wrapper.

The same applies to `Boolean`:

~~~java
Boolean enabled = null;
// if (enabled) { } // NullPointerException due to Boolean unboxing
if (Boolean.TRUE.equals(enabled)) {
    // Runs only when enabled is Boolean.TRUE
}
~~~

`Boolean.TRUE.equals(enabled)` is safe because the constant `Boolean.TRUE` is guaranteed non-null. It treats both null and false as “not enabled”, **which is only appropriate if business logic accepts merging them**. If null means “undetermined”, do not silently turn it into false without defining a policy.

## 5. Using short-circuit `&&` and `||` to check before unboxing

In conditions, Java evaluates `&&` and `||` from left to right and only evaluates the right-hand side when necessary. We can leverage this property to prevent null unboxing:

~~~java
Integer count = null;

boolean positive = count != null && count > 0; // false
boolean missingOrPositive = count == null || count > 0; // true
~~~

- With `&&`, if `count != null` is already false, the `count > 0` side is not executed.
- With `||`, if `count == null` is already true, the `count > 0` side is not executed.

**Condition order must not be reversed arbitrarily:**

~~~java
// count > 0 && count != null  // Wrong: can unbox null first
// count > 0 || count == null  // Wrong: can unbox null first
~~~

With the non-short-circuit boolean operators `&` or `|`, both sides are evaluated (when used on booleans), so the null-guard pattern above **does not** apply. This matters when refactoring conditions or building filter expressions.

A method checking for a positive nullable value can be written clearly:

~~~java
static boolean isPositive(Integer value) {
    return value != null && value > 0;
}
~~~

This method intentionally returns `false` if no value is present; that is a **business convention** that should be made explicit in the method name and documentation.

## 6. Choose a default or reject null?

`Objects.equals` serves **comparison**, not returning a replacement value. When an application needs to use a primitive, a concrete decision must be made for null.

### Option A — return a default value

~~~java
Integer optionalCount = null;
int safeCount = java.util.Objects.requireNonNullElse(optionalCount, 0);
// safeCount = 0
~~~

`Objects.requireNonNullElse(value, defaultValue)` returns the first value if non-null; otherwise it returns the default. **The default must also be non-null**; if both are null, it throws `NullPointerException`. For wrappers, this method returns a **wrapper**; in the example, assigning to `int` performs unboxing after a non-null default is obtained.

For expensive default-creation expressions, there is `Objects.requireNonNullElseGet(value, supplier)`; the supplier is invoked when the initial value is null and must return a non-null value. If the first argument already has a value, the supplier is not called.

A similar option is:

~~~java
int safeCount = optionalCount == null ? 0 : optionalCount;
~~~

The conditional operator here selects a safe primitive value after checking null. However, **do not** assume every null means 0: an unentered order total, an unknown age, and an exact quantity of 0 are usually distinct states.

### Option B — fail immediately at the boundary

~~~java
static int requireCount(Integer value) {
    return java.util.Objects.requireNonNull(value, "count is required");
}
~~~

This method throws `NullPointerException` with a message when null and unboxes after confirming an object exists. If null represents **invalid input**, you may prefer `IllegalArgumentException` or another business exception type per API conventions.

### Option C — preserve the missing state explicitly

If missing data is valid, you can keep a nullable `Integer`, use `Optional<Integer>` on certain return APIs, or model a distinct state. Define downstream rules: should computation halt, skip missing elements, or return an “insufficient data” result? Do not pick a sentinel value like `-1` or 0 if it could also be a real value.

## 7. Comparing nullable values in real-world spots

### DTOs and business objects

Suppose two requests have a nullable `Integer quantity` field. If you need to check whether the field changed compared to the old version:

~~~java
static boolean quantityChanged(Integer oldQuantity, Integer newQuantity) {
    return !java.util.Objects.equals(oldQuantity, newQuantity);
}
~~~

When both are null, the function returns false (unchanged); when only one side is null, it returns true; when both hold the same `Integer`, it returns false. This differs from a “null means 0” policy: if business logic treats null and 0 as identical, normalize **explicitly** before comparing.

### Collections and lookup

~~~java
java.util.List<Integer> values = java.util.Arrays.asList(1, null, 3);
boolean hasMissing = values.contains(null); // true
boolean hasThree = values.contains(3);      // true
~~~

Collections use equality according to element contracts; `List.contains` follows `equals`, so it can handle null if the collection implementation allows it. However, with `HashMap`/`HashSet` and wrapper keys, do not conflate `Integer(3)` with `Long(3)`; `Objects.equals` never erases this type boundary.

### Sorting a list containing null

~~~java
java.util.List<Integer> values =
        new java.util.ArrayList<>(java.util.Arrays.asList(3, null, 1));
values.sort(java.util.Comparator.nullsFirst(Integer::compare));
// [null, 1, 3]
~~~

`Integer::compare` compares non-null values; `Comparator.nullsFirst` handles null before delegating to the inner comparator. `nullsLast` can be used if missing values belong at the end of the list.

**Do not pass `Integer::compare` directly on a list containing null** without a wrapper handler: unboxing a null argument can throw `NullPointerException` during sorting.

## 8. `Objects.equals` with arrays and complex structured objects

Two arrays with different references yet identical elements are not considered equal by `Objects.equals`:

~~~java
Integer[] a = {1, null};
Integer[] b = {1, null};

boolean shallow = java.util.Objects.equals(a, b);     // false
boolean deep = java.util.Objects.deepEquals(a, b);    // true
~~~

Java arrays do not override `Object.equals` by content; `Objects.equals` therefore compares reference equality. `Objects.deepEquals` recognizes arrays and compares elements (including nested arrays) appropriately; or use `Arrays.equals`/`Arrays.deepEquals` according to the data shape. Do not assume the class name “Objects” automatically deep-compares every object: for custom classes, equality logic still depends on their `equals` implementation.

Be careful when writing classes with nullable wrapper fields: if writing a custom `equals`, `hashCode` should use the matching fields, such as `Objects.hash(fieldA, fieldB)`, to honor the contract that “two equal objects must have equal hash codes”. With Java `record`s, equality is auto-generated for components per language rules; you still must understand the meaning of null values and component types.

## 9. Complete runnable Java 17+ example

Save file `NullableWrapperDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class NullableWrapperDemo {
    public static void main(String[] args) {
        Integer missing = null;
        Integer ten = 10;
        Integer tenAgain = Integer.valueOf(10);
        Long tenLong = 10L;

        System.out.println("missing == null: " + (missing == null));
        System.out.println("equals(null,null): "
                + Objects.equals(null, null));
        System.out.println("equals(missing,ten): "
                + Objects.equals(missing, ten));
        System.out.println("equals(ten,missing): "
                + Objects.equals(ten, missing));
        System.out.println("equals(ten,tenAgain): "
                + Objects.equals(ten, tenAgain));
        System.out.println("equals(ten,tenLong): "
                + Objects.equals(ten, tenLong));
        System.out.println("equals(10,10L): "
                + Objects.equals(10, 10L));
        System.out.println("ten == 10: " + (ten == 10));
        System.out.println("safe AND: "
                + (missing != null && missing > 0));
        System.out.println("safe OR: "
                + (missing == null || missing > 0));

        try {
            int primitive = missing;
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unbox null: NullPointerException");
        }

        System.out.println("default zero: "
                + Objects.requireNonNullElse(missing, 0));

        List<Integer> list =
                new ArrayList<>(Arrays.asList(3, null, 1));
        list.sort(Comparator.nullsFirst(Integer::compare));
        System.out.println("sorted null first: " + list);

        Integer[] a = {1, null};
        Integer[] b = {1, null};
        System.out.println("arrays equals: " + Objects.equals(a, b));
        System.out.println("arrays deepEquals: "
                + Objects.deepEquals(a, b));

        System.out.println("Double NaN equals: "
                + Objects.equals(Double.NaN, Double.NaN));
        System.out.println("signed zero equals: "
                + Objects.equals(+0.0, -0.0));
        System.out.println("BigDecimal scale equals: "
                + Objects.equals(
                        new BigDecimal("1.0"),
                        new BigDecimal("1.00")));
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac NullableWrapperDemo.java
java NullableWrapperDemo
~~~

Stdout output:

~~~text
missing == null: true
equals(null,null): true
equals(missing,ten): false
equals(ten,missing): false
equals(ten,tenAgain): true
equals(ten,tenLong): false
equals(10,10L): false
ten == 10: true
safe AND: false
safe OR: true
unbox null: NullPointerException
default zero: 0
sorted null first: [null, 1, 3]
arrays equals: false
arrays deepEquals: true
Double NaN equals: true
signed zero equals: false
BigDecimal scale equals: false
~~~

The program verifies both null and non-null paths, different wrapper types, safe/unsafe unboxing, null sort ordering, and the difference between shallow and deep equality. Note that `try/catch` here is solely used to demonstrate the exception from null unboxing; **you should not use exception catching instead of null checks** as a routine control flow.

## 10. Limitations of `Objects.equals` to remember

- **Does not automatically turn null into 0:** `Objects.equals(null, 0)` is `false`; null remains an absent state.
- **Does not promote wrappers during equality:** `Objects.equals(10, 10L)` is `false` because `Integer` differs from `Long`.
- **Does not automatically compare arrays element-by-element:** use `Arrays.equals`, `Arrays.deepEquals`, or `Objects.deepEquals`.
- **Does not handle null inside other logic:** `Objects.equals(a, b)` does not make `a + 1` safe if `a == null`.
- **Does not resolve floating-point numbers by tolerance:** `Objects.equals(0.1 + 0.2, 0.3)` returns `false`; define a separate tolerance if the problem requires it.
- **Does not change `BigDecimal.equals`'s contract:** `new BigDecimal("1.0")` and `new BigDecimal("1.00")` have equal mathematical values under `compareTo == 0`, yet `equals` returns `false` because of differing scales.
- **Does not equate Boolean null with false:** `Objects.equals(null, Boolean.FALSE)` returns `false`; if using `Boolean.TRUE.equals(value)`, you are actively interpreting null as “not enabled” for that check.

Common bugs include writing `if (wrapper == 0)` before checking null, calling `wrapper.equals(other)` when the wrapper is nullable, relying on `==` to compare two wrappers' values, or forcing null values to defaults across too many system layers and losing track of where missing data originated.

## 11. Choosing approaches when building APIs

| Requirement | Approach | Points to watch |
| --- | --- | --- |
| Compare two nullable wrappers by object equality | `Objects.equals(a, b)` | Two nulls are equal; wrappers of different types are not automatically equal |
| Check if a wrapper is null | `value == null` or `value != null` | Does not unbox |
| Use a wrapper in arithmetic | Null guard then unbox | Error message/default per contract |
| Use a nullable Boolean in a condition | `Boolean.TRUE.equals(flag)` or three branches | Distinguish false from unknown if needed |
| Valid default value exists | `Objects.requireNonNullElse(value, defaultValue)` | Default must be non-null; avoid unintentionally masking missing data |
| Value is mandatory | `Objects.requireNonNull(value, message)` | Fail fast at the boundary |
| Sort a list containing null | `Comparator.nullsFirst/nullsLast` | Inner comparator only handles non-null |
| Array equality | `Arrays.equals` or `Objects.deepEquals` | Choose the right shallow/deep level |
| Cross-wrapper-type numeric comparison | Normalize according to a defined numeric range | Avoid casting every `Number` to `double` which loses precision |

## 12. Self-practice and answers

**Question 1.** Given `Integer x = null`, what are the results of `Objects.equals(x, null)` and `x == 0`?

**Answer:** `Objects.equals(x, null)` is `true`; `x == 0` attempts to unbox null and throws `NullPointerException`.

**Question 2.** What does `Objects.equals(Integer.valueOf(3), Long.valueOf(3L))` return? And `3 == 3L`?

**Answer:** The first call returns `false` due to different wrapper types; the primitive comparison returns `true` after numeric promotion.

**Question 3.** Given `Boolean approved = null`, write a condition that does not throw NPE and only accepts true.

**Answer:** `Boolean.TRUE.equals(approved)`. If null must be distinguished from false, add a separate handling branch.

**Question 4.** Why is `count != null && count > 0` safer than `count > 0 && count != null`?

**Answer:** `&&` evaluates from left to right and short-circuits. The first expression checks null beforehand; the second already unboxes before checking.

**Question 5.** Must two newly created `Integer[]` arrays with identical elements necessarily have `Objects.equals` return true?

**Answer:** No. `Objects.equals` uses array reference equality; use `Arrays.equals` or `Objects.deepEquals` to compare elements.

**Question 6.** If null must be treated as a “not provided” value, should it be replaced with 0 just to avoid NPE?

**Answer:** No, unless the business specification explicitly defines null as equivalent to 0. Keep nullable/`Optional` or reject invalid input to preserve data meaning.

## References

- [Java SE 21 — Objects.equals and deepEquals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html).
- [Java SE 21 — Integer.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)).
- [Java SE 21 — Boolean](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Boolean.html).
- [Java SE 21 — Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).
- [Java Language Specification `5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8).