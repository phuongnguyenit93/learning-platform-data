# Choosing Primitives vs. Wrappers Based on Data Requirements — Java 17+

## 1. Decision Principles

Java provides two related but **non-equivalent** forms:

- **Primitive types**, such as `int`, `boolean`, `double`: directly hold a value within the type's domain; **cannot accept `null`**.
- **Wrapper classes**, such as `Integer`, `Boolean`, `Double`: variables hold a **reference to a wrapper object** (or `null`), and can be used in generics, collections, and APIs requiring objects.

~~~java
int stock = 0;               // Has data: quantity is genuinely 0
Integer reportedStock = null; // No data yet, not the number 0

boolean enabled = false;     // Has data: state is off
Boolean approved = null;     // Not yet approved, not false
~~~

**The first decision question is not "which type is better?" but "is the data allowed to be absent?"**

If a value **must always exist** and is mainly used in calculations/conditions, a primitive is usually appropriate. If you need to **represent an absent state** or an API requires a reference type, a wrapper may be necessary. Even when choosing a wrapper, you must still clearly define how `null` is handled.

## 2. Table of the Eight Primitive and Wrapper Pairs

| Primitive | Wrapper | Typical Data Characteristics |
|---|---|---|
| `byte` | `Byte` | 8-bit signed integer |
| `short` | `Short` | 16-bit signed integer |
| `int` | `Integer` | 32-bit count/integer |
| `long` | `Long` | 64-bit integer |
| `float` | `Float` | 32-bit floating-point number |
| `double` | `Double` | 64-bit floating-point number |
| `char` | `Character` | Single UTF-16 code unit |
| `boolean` | `Boolean` | `true` or `false` value |

`String` is neither a primitive type nor the wrapper for `char`; it is a class representing a sequence of UTF-16 code units. `Void` plays a special role in certain reflection/generic APIs, but **there is no primitive `void` value to box like the pairs above**.

Example of automatic conversion (*autoboxing* and *unboxing*):

~~~java
int primitive = 12;
Integer boxed = primitive; // int -> Integer
int restored = boxed;      // Integer -> int

System.out.println(restored); // 12
~~~

Java's support for automatic conversion **does not erase** the differences between primitives and wrappers, especially the `null` state and how comparisons behave.

## 3. Decision Table by Data Requirements

| Requirement | Usually Preferred | Reason |
|---|---|---|
| Order quantity **must always have a value** | `int` | 0 is a valid quantity; no null state |
| Required integer ID, exceeding `int` limits | `long` | 64-bit integer range, no wrapper needed when non-nullable |
| Quantity **not yet entered or reported** | `Integer` | Distinguishes null from 0 |
| On/off flag with only two states | `boolean` | Exactly two states: `true`, `false` |
| Approval status with yes/pending/no | `Boolean` or `enum` | `null` can indicate undetermined; enum is clearer when states carry business meaning |
| API accepts or returns `List<Integer>` | `Integer` | Java 17 generics require reference types |
| Large array of measurements, heavy repeated math | `int[]`, `double[]` when appropriate | Avoids needing a wrapper per element |
| Returning an integer search result that may not exist | `OptionalInt` or clear nullable contract | Separates "not found" from value 0 |
| Required source data field not yet verified | Validate first, then primitive | Do not turn "unknown" into 0/false |
| Monetary amount needing exact decimal precision | `BigDecimal` or integer smallest unit | `Double` wrapper does not fix binary floating-point inaccuracy |

**Bottom line:** **presence/absence**, **value range**, **precision**, and **the APIs used** matter more than stylistic preference for writing a type. A wrapper type is not always slow/unsafe, nor does a primitive automatically make data valid for business logic.

## 4. Distinguishing "No Data" from Zero

Suppose an application tracks the number of confirmed orders:

- `confirmedOrders = 0`: the system confirms there are **zero orders**.
- `confirmedOrders = null`: **no report has been received yet**; it cannot be confirmed as 0.

~~~java
Integer confirmedOrders = null;

if (confirmedOrders == null) {
    System.out.println("no report");
} else {
    System.out.println("confirmed=" + confirmedOrders);
}
~~~

Output:

~~~text
no report
~~~

If you arbitrarily force missing data to 0:

~~~java
int count = confirmedOrders == null ? 0 : confirmedOrders;
~~~

then you **have decided to merge** two different states. That is only valid if business requirements genuinely permit treating "no report yet" as 0—for instance, a display labeled "default 0" with an explanation.

**API design rule:** if a value is required, validate upon receiving input or constructing the object rather than passing an arbitrary `Integer` deep into computation layers and hoping it is not `null`.

## 5. `Boolean` and the Three-State Problem

A `boolean` has exactly two values, `true`/`false`. With `Boolean`, the reference can also be `null`.

~~~java
Boolean approved = null;

if (approved == null) {
    System.out.println("pending");
} else if (approved) {
    System.out.println("approved");
} else {
    System.out.println("rejected");
}
~~~

Output:

~~~text
pending
~~~

This case makes sense when the data has **three states**: unreviewed, approved, rejected. However, if the system has more states (in review, on hold, locked...), using an `enum` is usually clearer:

~~~java
enum Decision {
    PENDING, APPROVED, REJECTED
}

Decision decision = Decision.PENDING;
~~~

**Do not abuse `null` as a "secret state"** when the API does not document its meaning. You can use a nullable wrapper, but the data contract and handling rules must be agreed upon and documented.

## 6. Default Values of Fields Differ from Local Variables

If a Java object is created **without explicitly initializing its fields**, primitive fields receive default values; reference fields default to `null`:

~~~java
static final class Defaults {
    int count;            // 0
    Integer optionalCount; // null
    boolean enabled;      // false
    Boolean optionalEnabled; // null
}
~~~

This is useful for understanding behavior, but **does not prove those default values are valid data**.

| Field | Default on Object Creation | Risk of Misinterpretation |
|---|---|---|
| `int count` | `0` | 0 may be confused with "data not loaded yet" |
| `Integer count` | `null` | Unboxing without checking will fail |
| `boolean enabled` | `false` | false may be confused with "not evaluated yet" |
| `Boolean enabled` | `null` | Must define how undetermined is handled |

**Local variables do not automatically receive default values:**

~~~java
static void example() {
    int count;
    // System.out.println(count); // Compile error: unassigned local variable
    count = 0;
    System.out.println(count); // 0
}
~~~

Initialize fields with meaningful values or use constructors to enforce supplying required values.

## 7. Encoding Data Requirements in the Model: Java 17 `record`

A `record` helps express the boundary between **required** and **optional/potentially missing** right in its signature:

~~~java
record Stock(String sku, int onHand, Integer reserved, Boolean approved) {
    Stock {
        java.util.Objects.requireNonNull(sku, "sku is required");
        if (onHand < 0) {
            throw new IllegalArgumentException("negative onHand");
        }
        if (reserved != null && reserved < 0) {
            throw new IllegalArgumentException("negative reserved");
        }
    }
}
~~~

Meaning:

- `onHand` is `int`: must have a value when constructing the record, yet still needs checking `onHand >= 0`.
- `reserved` is `Integer`: may not have received data yet (null), or may hold **0** or a positive number.
- `approved` is `Boolean`: may be unreviewed, `true`, or `false`.
- `sku` is a `String` reference: does not forbid null on its own, so the constructor calls `Objects.requireNonNull`.

~~~java
Stock unknown = new Stock("SKU-1", 10, null, null);
Stock knownZero = new Stock("SKU-1", 10, 0, false);

System.out.println(unknown.reserved() == null); // true
System.out.println(knownZero.reserved());         // 0
~~~

**Core point:** Java has no nullable primitive types. If absence must be represented, you need a mechanism in the model (wrapper, `OptionalInt` for return APIs, explicit state, result object...) and must enforce the business contract with validation.

## 8. Guarding `null` at Data Boundaries

An `Integer` or `Boolean` can contain `null`. When Java needs a primitive value to add, compare with a number, or run `if (flag)`, unboxing `null` causes `NullPointerException`. What must be decided in data design is whether missing input is **allowed** or **must be rejected**.

~~~java
static int requireCount(Integer count) {
    if (count == null) {
        throw new IllegalArgumentException("count is required");
    }
    return count; // Only unbox after checking
}
~~~

If null is a valid state, keep the wrapper until an explicit handling rule applies; do not default null to 0. The unboxing-null lesson analyzes ternary, short-circuit, and conditional traps in detail.

## 9. Comparing by Value or by Reference?

When two variables have type `Integer`, `a == b` asks whether they are the same object; caching can cause two wrappers for a small number to share an object. When you want to ask whether two **values** are equal, choose `a.equals(b)` if `a` is non-null, or `Objects.equals(a, b)` when both can be null.

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);
System.out.println(java.util.Objects.equals(first, second)); // true
~~~

With `Integer == int`, Java unboxes to compare numbers; if the wrapper is null, it causes an NPE. `Integer.equals(Long)` does not convert types to compare. The equality and cache lessons are the main references for these rules.

## 10. Generic Collections and Missing-Data Policies

`List<Integer>` holds wrappers because Java 17 generics use reference types. When converting to `int` for calculations, each element must have a value:

~~~java
java.util.List<Integer> readings =
        java.util.Arrays.asList(2, null, 3);
int sum = 0;
for (Integer n : readings) {
    if (n != null) {
        sum += n;
    }
}
System.out.println(sum); // 5
~~~

Skipping null here is an **illustrative policy**, not the right default for every system. `List.of(...)` does not accept null elements. If numeric data is always required, involves heavy calculation, and does not depend on generics, primitive arrays or primitive streams may make more sense; the performance section below explains how to evaluate this.

## 11. `OptionalInt` for APIs Returning Potentially Absent Results

Sometimes the caller needs to know **whether an integer result exists**, without returning a nullable `Integer`. Java provides `java.util.OptionalInt`:

~~~java
import java.util.OptionalInt;

static OptionalInt findScore(boolean found) {
    return found ? OptionalInt.of(0) : OptionalInt.empty();
}
~~~

Caller side:

~~~java
OptionalInt missing = findScore(false);
OptionalInt existingZero = findScore(true);

System.out.println(missing.isEmpty());     // true
System.out.println(existingZero.orElse(-1)); // 0
~~~

`OptionalInt.empty()` is **different** from `OptionalInt.of(0)`. An API using `OptionalInt` expresses presence/absence directly in its return type.

**Practical consideration:** `OptionalInt` fits best as the **return type of a method** that may have no result. Do not blindly replace every `Integer` field with an `OptionalInt` field, because frameworks, data formats, or existing codebases may have their own conventions. Choose based on the API contract and ecosystem in use.

## 12. Primitives and Wrappers: Performance and Memory

Wrappers are reference objects and can incur **boxing/unboxing**, reference storage, allocation, and garbage-collection pressure depending on the scenario.

~~~java
int[] primitiveArray = new int[1_000];
Integer[] wrapperArray = new Integer[1_000];
~~~

The two structures **differ in meaning**:

- `int[]` holds 1000 `int` values, each element defaulting to 0.
- `Integer[]` holds 1000 **references**, each element initially null. Creating the array does **not** automatically create 1000 `Integer` objects.
- Memory layout, headers, and object alignment depend on the JVM; do **not** deduce actual total RAM solely from `Integer.SIZE`.

In high-volume numeric processing, primitive arrays and primitive streams (`IntStream`, `LongStream`, `DoubleStream`) can help avoid unnecessary wrappers:

~~~java
int total = java.util.stream.IntStream.of(2, 3, 5).sum();
System.out.println(total); // 10
~~~

However, you should **not** claim that every primitive is always faster than every wrapper on every JVM. The JIT can optimize, caches can reuse wrappers, and performance also depends on the workload. When optimization truly matters, measure with a proper benchmark (such as JMH).

**Principle:** prioritize the right data model first; when multiple choices are correct, consider simplicity and measure actual performance.

## 13. Wrappers Do Not Solve Decimal Precision Problems

Choosing `Double` instead of `double` only changes **how the value is boxed and nullability**, not the **binary floating-point** representation rules:

~~~java
double primitive = 0.1 + 0.2;
Double boxed = primitive;

System.out.println(primitive); // 0.30000000000000004
System.out.println(boxed);     // 0.30000000000000004
~~~

If business rules require exact decimal monetary calculations, choose a model such as `BigDecimal` or an integer representing the smallest unit:

~~~java
java.math.BigDecimal exact =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(exact); // 0.3
~~~

**Separate two independent decisions:**

1. Can the value be **missing**? → primitive vs. wrapper/result type with an absent state.
2. What **precision and range** does the value need? → int/long/double/BigDecimal/... based on math and business needs.

Using a wrapper just because it "looks more accurate than a primitive" is fundamentally wrong.

## 14. API Design: State Null Contracts and Validation Explicitly

Example of a method accepting a quantity that is allowed to be missing:

~~~java
static String describeCount(Integer count) {
    return count == null ? "not reported" : "count=" + count;
}
~~~

This makes sense when **missing is a valid state**. Conversely, if data must have a quantity, declare a primitive:

~~~java
static boolean hasStock(int count) {
    if (count < 0) {
        throw new IllegalArgumentException("negative stock");
    }
    return count > 0;
}
~~~

A wrapper field does not necessarily allow `null`, and a default primitive is not necessarily valid. **Data design must align with validation**.

APIs receiving external data (JSON, database, HTTP request, forms...) may also distinguish **field omitted**, **null sent**, **0 sent**, or **string "0" sent**. Exact mapping depends on the framework, schema, and API conventions; never assume every Java framework converts them into primitives/wrappers the same way.

When receiving wrappers from an outer layer, validate/normalize at the boundary before passing into internal logic that requires primitives.

## 15. Standalone Java 17 Program: Choosing Types for Real Requirements

Create the file with the exact name **`PrimitiveOrWrapperDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;

public final class PrimitiveOrWrapperDemo {
    private PrimitiveOrWrapperDemo() {}

    static final class Defaults {
        int count;
        Integer optionalCount;
        boolean enabled;
        Boolean optionalEnabled;
    }

    record Stock(String sku, int onHand, Integer reserved, Boolean approved) {
        Stock {
            Objects.requireNonNull(sku, "sku is required");
            if (onHand < 0) {
                throw new IllegalArgumentException("negative onHand");
            }
            if (reserved != null && reserved < 0) {
                throw new IllegalArgumentException("negative reserved");
            }
        }
    }

    static String approvalLabel(Boolean approved) {
        if (approved == null) {
            return "unknown";
        }
        return approved ? "approved" : "rejected";
    }

    static int sumPresent(List<Integer> values) {
        int total = 0;
        for (Integer value : values) {
            if (value != null) {
                total += value;
            }
        }
        return total;
    }

    static OptionalInt findCount(boolean found) {
        return found ? OptionalInt.of(0) : OptionalInt.empty();
    }

    public static void main(String[] args) {
        Defaults defaults = new Defaults();
        System.out.println("default int=" + defaults.count);
        System.out.println("default Integer=" + defaults.optionalCount);
        System.out.println("default boolean=" + defaults.enabled);
        System.out.println("default Boolean=" + defaults.optionalEnabled);

        Stock unknown = new Stock("SKU-1", 10, null, null);
        Stock explicit = new Stock("SKU-1", 10, 0, false);
        System.out.println("required stock=" + unknown.onHand());
        System.out.println("missing reserved=" + (unknown.reserved() == null));
        System.out.println("reported reserved zero=" + explicit.reserved());
        System.out.println("approval unknown=" + approvalLabel(unknown.approved()));
        System.out.println("approval false=" + approvalLabel(explicit.approved()));
        System.out.println("approval true=" + approvalLabel(true));

        List<Integer> readings = Arrays.asList(2, null, 3);
        System.out.println("sum present=" + sumPresent(readings));

        Integer first = Integer.valueOf(1000);
        Integer second = Integer.valueOf(1000);
        Integer alias = first;
        System.out.println("wrapper value equality="
                + Objects.equals(first, second));
        System.out.println("same wrapper alias=" + (first == alias));

        Integer counter = 3;
        Integer snapshot = counter;
        counter++;
        System.out.println("wrapper counter=" + counter);
        System.out.println("wrapper snapshot=" + snapshot);

        Integer missing = null;
        try {
            int invalid = missing;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing rejected");
        }

        OptionalInt absent = findCount(false);
        OptionalInt presentZero = findCount(true);
        System.out.println("optional absent=" + absent.isEmpty());
        System.out.println("optional zero=" + presentZero.orElse(-1));

        double binarySum = 0.1 + 0.2;
        Double wrappedSum = binarySum;
        System.out.println("double result=" + wrappedSum);
        System.out.println("decimal exact="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        try {
            new Stock("SKU-X", -1, null, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative stock rejected");
        }
    }
}
~~~

**Requirements:** JDK 17+; open terminal in the directory containing the file. No Maven, Gradle, or libraries outside the JDK are needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveOrWrapperDemo.java
java -cp . PrimitiveOrWrapperDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveOrWrapperDemo.java
java -cp . PrimitiveOrWrapperDemo
~~~

**Exact expected output:**

~~~text
default int=0
default Integer=null
default boolean=false
default Boolean=null
required stock=10
missing reserved=true
reported reserved zero=0
approval unknown=unknown
approval false=rejected
approval true=approved
sum present=5
wrapper value equality=true
same wrapper alias=true
wrapper counter=4
wrapper snapshot=3
null unboxing rejected
optional absent=true
optional zero=0
double result=0.30000000000000004
decimal exact=0.3
negative stock rejected
~~~

**Points to verify yourself:**

1. Primitive fields `int`/`boolean` default to 0/false; wrapper fields default to null.
2. The same `Integer` type distinguishes `reserved=null` and `reserved=0`.
3. `Boolean` allows an unknown state alongside false/true, if the API has a matching contract.
4. The `List<Integer>` loop intentionally skips null **per the example's policy**.
5. Comparing wrappers for 1000 via `Objects.equals` does not rely on identity caching; `first == alias` is true because they truly share the same reference.
6. Incrementing `counter` does not modify the wrapper object held by `snapshot`.
7. Null unboxing is caught intentionally, illustrating why data must be checked.
8. `OptionalInt.empty()` differs from `OptionalInt.of(0)`.
9. The `Double` wrapper does not make decimal addition exact; `BigDecimal` from strings serves a different model.
10. The constructor rejects negative quantities, showing that choosing the right type still requires validation.

## 16. Common Mistakes and How to Fix Them

| Mistake or Assumption | Problem | Appropriate Approach |
|---|---|---|
| Using `int` for "not yet entered" data and silently using 0 | Merges missing data with 0 | Use `Integer`/explicit absent state |
| Using `Integer` for every counter variable | Increases null-checking/boxing needs | Use `int` when data is required and math-heavy |
| `Boolean flag = null; if (flag)` | Unboxing null causes NPE | Check for null or design an enum |
| `Integer n = null; int x = n;` | Unboxing null causes NPE | Validate or choose a clear policy |
| Comparing two `Integer`s with `==` when wanting numeric comparison | `==` compares identity of two references | `equals`/`Objects.equals` |
| Treating default field `int = 0` as valid data | JVM default is not business validation | Constructor/validation |
| Treating `Integer = null` as equivalent to 0 | Loses the meaning "no data yet" | Keep and handle null separately |
| Using `List<int>` | Java 17 generics do not accept primitives | `List<Integer>` |
| Iterating `List<Integer>` with `for (int n : list)` when nulls exist | Unboxing null inside loop | Validate or handle each `Integer` |
| Using `OptionalInt` regardless of API/framework | Differs from integration conventions/contracts | Use appropriately in return types |
| Using `Double` instead of `double` to fix decimal errors | Wrapper does not change binary representation | `BigDecimal` or integer smallest unit |
| Assuming wrappers always allocate new objects on boxing | JVM may cache/optimize | Do not depend on identity/allocation |
| Using primitives to avoid all data errors | Primitives still have limits/overflow/invalid values | Validation and choosing proper range |
| Automatically converting null → 0 everywhere | Can corrupt business meaning | Agree on a default policy first |

## 17. Short Exercises and Answers

### Exercise A — Reported Quantity

How does `count=0` differ from `count=null` in an inventory tracking system?

**Answer:** `0` means there is a report confirming the quantity is zero; `null` can signify no figures have been reported yet (if the API contract defines it that way). When these two states must be distinguished, `Integer` or a type with an absent state is appropriate.

### Exercise B — Primitive or Wrapper for a Status Flag?

An API only has on/off, with no unknown state. Choose `boolean` or `Boolean`?

**Answer:** usually choose `boolean`. If the API has a separate "not yet reviewed" state, you can use `Boolean` with null rules or an `enum` with explicit state names.

### Exercise C — Null and Unboxing

~~~java
Integer n = null;
// System.out.println(n + 1);
~~~

**Answer:** if the commented line is enabled, it will compile but throw `NullPointerException` at runtime, because addition must unbox `n` to `int` first.

### Exercise D — Comparing Values

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(java.util.Objects.equals(a, b));
~~~

**Answer:** `true`. Uses value-based equality, without depending on the object cache range.

### Exercise E — Generics

~~~java
java.util.List<Integer> nums = java.util.List.of(2, 3);
int sum = 0;
for (int n : nums) {
    sum += n;
}
System.out.println(sum);
~~~

**Answer:** `5`. The list holds wrappers; each element is unboxed when assigned to the `int` loop variable. For `List.of`, null must not be placed in the list.

### Exercise F — Choosing Type and Business Range

An `age` field must always be provided and must be non-negative. Is using `int` sufficient to guarantee valid data?

**Answer:** **not sufficient**. `int` eliminates nullability, but it can still hold negative numbers. You must check `age >= 0` at the input boundary or constructor.

## 18. Checklist and Conclusion

- [ ] Know Java's eight primitive–wrapper pairs.
- [ ] Understand primitives cannot hold `null`, whereas wrappers can.
- [ ] Distinguish data equal to 0/false from missing data.
- [ ] Choose primitives when values are required and primarily computed.
- [ ] Choose wrappers when nullability is genuinely needed or APIs/generics require reference types.
- [ ] Know that default primitive and wrapper fields differ; local variables must be assigned before reading.
- [ ] Know boxing/unboxing and handle null before unboxing.
- [ ] Do not compare the values of two wrappers using `==`.
- [ ] Validate input/data range even when choosing primitives.
- [ ] Understand how `List<Integer>` differs from `int[]`, and watch for null in collections.
- [ ] Know `OptionalInt` is an option for methods returning potentially absent results.
- [ ] Do not mistake `Double` wrapper for a solution to exact decimal arithmetic.
- [ ] Know how to consider memory/performance based on workload, not just intuition.
- [ ] Run `PrimitiveOrWrapperDemo.java` on Java 17+ and compare every line of expected output.

**Conclusion:** Choosing **primitive** vs. **wrapper** depends first on **data meaning**: required or potentially absent. Primitives suit values that always exist and direct calculations; wrappers suit nullable values, collections, and APIs needing objects. Regardless of which type you choose, you still must specify valid ranges, null handling, comparison rules, and precision appropriate to actual requirements.