# NullPointerException When Unboxing Null Values in Java

In Java, **unboxing** is the operation of converting a wrapper object, such as `Integer`, `Long`, or `Double`, into its corresponding primitive value `int`, `long`, or `double`. When the wrapper object is `null`, **there is no primitive value to extract**. If Java performs unboxing on that value, the program throws **`NullPointerException` (NPE)** at runtime.

Shortest example:

```java
Integer quantity = null;
int count = quantity; // NullPointerException at runtime.
```

The assignment line looks like a valid automatic conversion. It **compiles successfully**, yet at runtime it is semantically equivalent to calling the wrapper's value extraction method, such as `quantity.intValue()`; that call cannot execute on a `null` reference.

The tricky part of this topic is that **unboxing often happens implicitly**: you do not need to write `intValue()`; operators like `+`, `++`, `==`, the ternary operator, argument passing, or retrieving data from a collection can all trigger it.

This lesson belongs to the **Boxing and unboxing** section in **Java core – numbers**. The goal is to understand accurately **when unboxing happens**, why NPEs appear, how to distinguish missing data from 0, and how to design safe APIs.

## 1. Boxing, unboxing, and differences between primitives and wrappers

| Primitive | Corresponding wrapper | Can it be `null`? | Example |
| --- | --- | --- | --- |
| `byte` | `Byte` | Primitive: no; wrapper: yes | `Byte b = null;` |
| `short` | `Short` | Primitive: no; wrapper: yes | `Short s = null;` |
| `int` | `Integer` | Primitive: no; wrapper: yes | `Integer n = null;` |
| `long` | `Long` | Primitive: no; wrapper: yes | `Long n = null;` |
| `float` | `Float` | Primitive: no; wrapper: yes | `Float f = null;` |
| `double` | `Double` | Primitive: no; wrapper: yes | `Double d = null;` |
| `char` | `Character` | Primitive: no; wrapper: yes | `Character c = null;` |
| `boolean` | `Boolean` | Primitive: no; wrapper: yes | `Boolean b = null;` |

`Integer` is not just another name for `int`:

- An `int` variable stores an integer value; it cannot hold `null`.
- An `Integer` variable is a **reference to an object**. This reference can be `null`.
- **Boxing** converts a primitive value into a wrapper, e.g., `Integer boxed = 7;`.
- **Unboxing** extracts a primitive value from a wrapper, e.g., `int value = boxed;`.
- Boxing a valid primitive does not produce `null`, but a wrapper received from a parameter, database, map, or DTO can be `null`.

```java
int count = 7;
Integer boxed = count;     // Autoboxing.
int unboxed = boxed;       // Auto-unboxing, safe because boxed is non-null.
```

Compare with:

```java
Integer boxed = null;
int unboxed = boxed;       // NPE during unboxing.
```

**An NPE is not an out-of-range error** and has nothing to do with `Integer.MIN_VALUE`, overflow, or precision. It is an error caused by **accessing a value through a reference that does not point to an object**.

### 1.1. Why does the compiler not reject it?

The static type of `boxed` is `Integer`, which is valid to convert to `int`. The compiler cannot assume every `Integer` is non-`null` at runtime. For example, the value may come from a parameter, a method result, or a conditional branch.

```java
static int consume(Integer value) {
    return value; // Compiles; only throws NPE if value is null at runtime.
}
```

Java does not automatically insert a default value of 0 when unboxing `null`, because doing so would **equate “no data” with “value equals 0”**.

## 2. Direct operations that trigger null unboxing

### 2.1. Assigning to a primitive variable

```java
Integer optionalCount = null;
// int count = optionalCount; // At runtime: NPE.
```

The left-hand side `int` demands a primitive value, so Java must unbox the right-hand side.

### 2.2. Calling a method with a primitive parameter

```java
static void printCount(int count) {
    System.out.println(count);
}

// Integer nullableCount = null;
// printCount(nullableCount); // NPE before printCount body executes.
```

Calling `printCount(nullableCount)` requires converting `Integer` to `int` to pass the parameter. The exception happens **when evaluating the argument**, before the method gets a chance to check the value itself.

Designing two different APIs:

```java
static void acceptRequiredCount(int count) {
    // No null: caller must supply an integer.
}

static void acceptNullableCount(Integer count) {
    if (count == null) {
        // Handle missing state.
        return;
    }
    int primitive = count;
    // ...
}
```

If data is required, using primitives at the boundary after validation helps reduce NPE risks in deeper layers. If missing data is a valid state, the API accepts a wrapper but must include a separate handling branch.

### 2.3. Calling intValue() directly

```java
Integer number = null;
// int value = number.intValue(); // NPE.
```

This is **explicit** unboxing. This syntax does not produce a different exception from implicit unboxing; the essence is the same attempt to retrieve a value from a `null` reference.

## 3. Arithmetic operations automatically unbox wrapper operands

An expression looking as simple as:

```java
Integer quantity = null;
int total = quantity + 1; // NPE.
```

still must perform unboxing so the `+` operator receives numeric values. The same holds for subtraction, multiplication, division, remainder, and expressions using integer operations.

```java
Integer amount = null;

// int a = amount * 2; // NPE.
// int b = amount / 2; // NPE.
// int c = amount % 2; // NPE.
// boolean positive = amount > 0; // NPE.
```

When `amount` is `null`, no primitive operation actually executes before the exception arises. Do not confuse this with the case where `amount` is valid but the divisor is 0: that can throw `ArithmeticException` after unboxing succeeds.

### 3.1. ++, --, and compound assignment also unbox

```java
Integer count = null;
// count++; // NPE.
// ++count; // NPE.
// count += 1; // NPE.
```

Update operators require retrieving the wrapper's current value, performing the increment/decrement or addition, and then boxing the new value into the reference variable. If the old value is `null`, the operation fails right at the unboxing step.

A non-null example:

```java
Integer count = 3;
count++;                // Unbox 3, add 1, box Integer 4.
System.out.println(count); // 4
```

Key point: `Integer` does not automatically become a primitive type just because `++` is used. The variable still has a wrapper type and can be assigned `null` at another point.

### 3.2. Receiving a wrapper from an operation does not make the expression “null-safe”

```java
Integer a = 10;
Integer b = null;

// Integer result = a + b; // NPE when unboxing b.
```

Even though the receiving variable has type `Integer`, the **arithmetic addition operator** on `Integer` unboxes the operands, computes according to numeric promotion, and boxes the result if needed. Having a wrapper on the result variable **does not** make addition know how to handle `null`.

## 4. Equality comparison: why might Integer == Integer not unbox?

This is the opposite trap: there are cases where `==` does **not** unbox. You must consider **the types of both operands**, not just look at the operator name.

### 4.1. Both operands are Integer: reference comparison

```java
Integer left = null;
Integer right = null;

System.out.println(left == right); // true: both are null.
```

Here, both operands have **reference type `Integer`**. `==` performs reference comparison, requiring no unboxing. Therefore two `null` values are treated as the same `null` reference and do not throw an NPE.

However, reference comparison is not the standard way to compare the **numeric values** of two wrappers:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true
// a == b compares identity, not a value comparison contract.
```

Wrapper caching cases can make `==` coincidentally return true; do not rely on that to decide whether two numbers are equal.

### 4.2. One side is a primitive: unboxing occurs

```java
Integer left = null;

// boolean same = left == 0; // NPE.
```

Because the right-hand side `0` is a primitive `int`, Java applies numeric promotion/unboxing rules to compare numbers. `left` must become an `int`; if it is `null`, an NPE occurs.

Distinction table:

| Expression | Unboxing? | Behavior |
| --- | --- | --- |
| `Integer a = null, b = null; a == b` | No | `true` (reference comparison) |
| `Integer a = null; a == 0` | Yes | NPE |
| `Integer a = null; a < 0` | Yes | NPE |
| `Integer a = null; Objects.equals(a, null)` | No | `true` |
| `Integer a = null; a.equals(0)` | No mandatory unboxing step | NPE due to **calling a method on a null receiver** |
| `Integer a = 5; int n = 5; a == n` | Yes | `true` after unboxing |

There are at least **two paths leading to NPE** to distinguish: one is **unboxing null**, and two is **calling a method on a null object**, such as `a.equals(...)`. Both throw `NullPointerException` but have different immediate causes.

### 4.3. Choosing how to compare

- For **two nullable wrappers**, use `Objects.equals(a, b)` if you want null-safety and value comparison under the `equals` contract.
- For wrappers that must not be null, validate first and then unbox; from there you can use numeric comparison.
- Do not use `==` between two `Integer`s as a substitute for `equals`; it compares identity and may be affected by caching.
- `Objects.equals(Integer.valueOf(1), Long.valueOf(1L))` is `false` because the two wrappers have different types. To compare **numeric values of different types**, choose explicit conversion rules after checking null and value ranges.

## 5. The ?: ternary operator can unbox even if the receiving variable is a wrapper

The conditional operator `condition ? expression1 : expression2` determines **the type of the result expression** from its two branches, not simply from the receiving variable's type. When one branch is a numeric wrapper and the other is a primitive, type selection rules can force the wrapper to unbox.

```java
Integer nullable = null;
boolean chooseNullable = true;

// int result = chooseNullable ? nullable : 0; // NPE if the nullable branch is chosen.
```

If the two branches have types `Integer` and `int` as above, the numeric result is `int`, so the `nullable` branch must unbox when chosen.

What often surprises developers is that changing the receiving variable to a wrapper **does not necessarily prevent this**:

```java
Integer nullable = null;
boolean chooseNullable = true;

// Integer result = chooseNullable ? nullable : 0;
// Can still NPE because the conditional operation already has type int before boxing to Integer.
```

If the intent is to **preserve the missing state**, make both branches have the reference type `Integer`:

```java
Integer nullable = null;
boolean chooseNullable = true;
Integer result = chooseNullable ? nullable : null;
// result == null; no unboxing.
```

Or better yet, write explicit business branches:

```java
Integer result;
if (chooseNullable) {
    result = nullable;
} else {
    result = Integer.valueOf(0);
}
```

**No need to fear every ternary operator**: only the chosen branch is evaluated at runtime. However, rules determining **the common expression type** can cause that branch's wrapper value to be unboxed.

## 6. Map, DTO, JDBC, and missing data

### 6.1. Map.get can return null

```java
Map<String, Integer> counts = new HashMap<>();
Integer found = counts.get("missing"); // null when there is no mapping.
```

If you continue:

```java
// int n = counts.get("missing"); // NPE due to unboxing null.
```

The result of `Map.get` is normally a wrapper, because Java collections do not hold primitives directly. If the key does not exist, `get` returns `null` by contract. A `HashMap` can also store a mapping from a key to a **null value**.

### 6.2. getOrDefault does not always replace null values

```java
Map<String, Integer> counts = new HashMap<>();
counts.put("present-null", null);

int missing = counts.getOrDefault("missing", 7); // 7
// int present = counts.getOrDefault("present-null", 7); // NPE.
```

`Map.getOrDefault(key, defaultValue)` uses the default value when **there is no mapping for the key**. If the key has a mapping to `null`, the method returns that `null` and does not necessarily apply the default. Assigning directly to `int` then causes an NPE.

Three states must be distinguished by contract:

| State | `containsKey(key)` | `get(key)` |
| --- | --- | --- |
| Key does not exist | `false` | `null` |
| Key exists, value is null | `true` | `null` |
| Key exists, value is 0 | `true` | `Integer.valueOf(0)` |

If zero and absent data carry different meanings, **do not merge them just to avoid NPE**.

### 6.3. From database/JSON/DTO

An optional numeric field in a DTO can be represented by `Integer` or `Long`. When the source returns `null`, the wrapper holds null; subsequently an operation or assignment to a primitive can make the program throw an NPE.

Example DTO class:

```java
final class OrderInput {
    Integer quantity; // Can be null if the source does not provide a value.
}
```

`quantity == null` does not mean `quantity == 0`. Depending on the specification:
- **Required:** report a validation error when absent before computing.
- **Optional with default 0:** apply an explicit default at the input boundary.
- **Optional where missing has its own meaning:** keep the wrapper or a data model representing the missing state.

When working with JDBC, understand SQL `NULL` columns, data retrieval methods, and checking `wasNull()` if an API returns primitive types; do not assume every SQL NULL read will automatically produce a null wrapper as intended.

## 7. Wrapper arrays and streams prone to NPE

### 7.1. Wrapper arrays initialize with null elements

```java
Integer[] wrappers = new Integer[3];
// wrappers[0], wrappers[1], wrappers[2] are all null.

// int first = wrappers[0]; // NPE on unbox.

int[] primitives = new int[3];
// primitives[0], primitives[1], primitives[2] are all 0.
```

This is a difference in **default values** of array elements: wrapper arrays hold initial null references, whereas primitive arrays have a default primitive value of 0.

For an unassigned **local variable** `int x;`, Java does not allow reading it immediately: that is a **compile-time error “variable might not have been initialized”**, not a variable defaulting to 0. Only fields and array elements have default values under initialization rules.

### 7.2. Stream<Integer> to IntStream

A pipeline containing `null`:

```java
Stream<Integer> stream = Stream.of(1, null, 3);
// int sum = stream.mapToInt(Integer::intValue).sum(); // NPE.
```

The method reference `Integer::intValue` must call the method on each element; if an element is null, an NPE occurs.

If **business rules allow ignoring missing elements**:

```java
int sum = Stream.of(1, null, 3)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
```

Filtering out null values is a **business decision**, not a safe default in every problem. If missing data is an error, validate and report an error instead of silently filtering it out, since sample counts and sums can be altered.

## 8. How to handle null before unboxing

### 8.1. Direct check: when null is invalid

```java
static int requiredQuantity(Integer quantity) {
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return quantity; // Safe unboxing after check.
}
```

The advantage is that the error is reported close to the data source and the exception describes the **business rule**, rather than letting an NPE appear deep inside a calculation. The contract can choose another exception type, but it must be consistent.

### 8.2. Allow a default when null means “not provided”

```java
Integer quantity = null;
int count = quantity != null ? quantity : 0;
```

The `quantity` branch is unboxed only when non-null; the default branch provides primitive 0. This snippet is an intentional choice of a default.

Java 9+ provides:

```java
int count = Objects.requireNonNullElse(quantity, 0);
```

`Objects.requireNonNullElse` returns the first argument if non-null, or the default value (which must be non-null). The `Integer` result is safely unboxed when the default is 0.

### 8.3. Optional<Integer>

```java
int count = Optional.ofNullable(quantity).orElse(0);
```

`Optional` can be useful in APIs that want to express optionality, but it **does not automatically justify** replacing missing values with 0. If missing input must report an error:

```java
int count = Optional.ofNullable(quantity)
        .orElseThrow(() -> new IllegalArgumentException("quantity required"));
```

When `orElseThrow` is called, the returned `Integer` value is non-null if data exists; otherwise, the business exception is raised.

**Do not call `Optional.get()` blindly** hoping it solves null. `Optional.empty().get()` has its own error (`NoSuchElementException`), and you still need to decide the semantics of absent data.

### 8.4. Objects.requireNonNull is fail-fast detection, not providing a default

```java
Integer quantity = null;
// int count = Objects.requireNonNull(quantity, "quantity must not be null");
// Throws NullPointerException with the message you supplied.
```

`requireNonNull` is useful when you want to **fail fast** and keep the NPE contract for required parameters. It does not turn null into 0 and is not the only approach; at business requirement boundaries, `IllegalArgumentException` or a validation error often carries clearer meaning.

## 9. Distinguishing null, zero, and invalid data

An important design point:

- `null`: **no object/no value** in a position permitting a null reference.
- `0`: **a valid integer value**, meaning a quantity of zero.
- A negative number in a quantity field: may be a type-valid integer value but **violates business rules**.
- A non-numeric string: an input conversion error, not null unboxing.

Example shopping cart API:

| Quantity input | Suggested meaning | How to handle |
| --- | --- | --- |
| `null` | Required field not provided | Return validation error |
| `0` | Provided, but zero items selected | May be rejected or accepted depending on contract |
| `3` | Quantity of three items | Valid if within allowed limits |
| `-3` | Negative | May be rejected by business rules |

If `null → 0` is defaulted everywhere, the system can mask data source bugs, making it hard to detect a field accidentally omitted in an API update.

**Preferred design:** convert nullable DTOs into validated domain data right at the boundary, then use primitives if the “missing data” meaning no longer exists.

## 10. Standalone Java 17+ program

Save the following content into the file **`NullUnboxingDemo.java`**. Error-causing cases are caught individually so the program runs to completion, helping observe exactly where NPEs occur.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Stream;

public class NullUnboxingDemo {
    static int requiredQuantity(Integer quantity) {
        if (quantity == null) {
            throw new IllegalArgumentException("quantity is required");
        }
        return quantity;
    }

    public static void main(String[] args) {
        Integer boxed = null;

        try {
            int direct = boxed;
        } catch (NullPointerException ex) {
            System.out.println("direct-unbox=NPE");
        }

        try {
            int added = boxed + 1;
        } catch (NullPointerException ex) {
            System.out.println("arithmetic=NPE");
        }

        try {
            boxed++;
        } catch (NullPointerException ex) {
            System.out.println("increment=NPE");
        }

        Integer anotherNull = null;
        System.out.println("wrapper-reference-equality=" +
                (boxed == anotherNull));

        try {
            boolean equalsZero = boxed == 0;
        } catch (NullPointerException ex) {
            System.out.println("primitive-comparison=NPE");
        }

        System.out.println("objects-null-equality=" +
                Objects.equals(boxed, null));

        boolean selectNull = true;
        try {
            int selected = selectNull ? boxed : 0;
        } catch (NullPointerException ex) {
            System.out.println("ternary=NPE");
        }

        Integer retainedNull = selectNull ? boxed : null;
        System.out.println("nullable-ternary=" + retainedNull);

        Integer[] wrappers = new Integer[1];
        try {
            int arrayValue = wrappers[0];
        } catch (NullPointerException ex) {
            System.out.println("wrapper-array=NPE");
        }
        int[] primitives = new int[1];
        System.out.println("primitive-array=" + primitives[0]);

        Map<String, Integer> map = new HashMap<>();
        map.put("present-null", null);
        System.out.println("missing-default=" +
                map.getOrDefault("missing", 7));

        try {
            int present = map.getOrDefault("present-null", 7);
        } catch (NullPointerException ex) {
            System.out.println("mapped-null=NPE");
        }
        System.out.println("mapping-exists=" +
                map.containsKey("present-null"));

        try {
            int streamSum = Stream.of(1, null, 3)
                    .mapToInt(Integer::intValue)
                    .sum();
        } catch (NullPointerException ex) {
            System.out.println("stream=NPE");
        }

        int validSum = Stream.of(1, null, 3)
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("filtered-sum=" + validSum);

        System.out.println("fallback=" +
                Objects.requireNonNullElse(boxed, 0));
        System.out.println("optional-fallback=" +
                Optional.ofNullable(boxed).orElse(5));

        try {
            requiredQuantity(boxed);
        } catch (IllegalArgumentException ex) {
            System.out.println("required-validation=error");
        }
        System.out.println("zero-is-valid-value=" +
                (requiredQuantity(0) == 0));
    }
}
```

Compile and run commands with JDK 17+:

```bash
javac NullUnboxingDemo.java
java NullUnboxingDemo
```

Stdout:

```text
direct-unbox=NPE
arithmetic=NPE
increment=NPE
wrapper-reference-equality=true
primitive-comparison=NPE
objects-null-equality=true
ternary=NPE
nullable-ternary=null
wrapper-array=NPE
primitive-array=0
missing-default=7
mapped-null=NPE
mapping-exists=true
stream=NPE
filtered-sum=4
fallback=0
optional-fallback=5
required-validation=error
zero-is-valid-value=true
```

**Explanation of key results:**

1. `direct-unbox`, `arithmetic`, and `increment` are all NPEs from unboxing null, despite very different syntax.
2. `wrapper-reference-equality=true` produces no NPE because `boxed == anotherNull` compares **two `Integer` references**.
3. `primitive-comparison=NPE` because `boxed == 0` requires unboxing `Integer` to `int`.
4. The ternary operator returns `int` in an expression mixing `Integer` and `int`, causing an NPE when the null wrapper branch is selected. An expression with two `Integer`/`null` reference branches retains null.
5. A new `Integer[]` array holds null elements; a new `int[]` array holds 0.
6. `getOrDefault` does not replace null in an **existing mapping**; `containsKey` shows this is not a missing key.
7. Filtering in the stream removes null **because the program intentionally permits skipping** values with no data.
8. `requireNonNullElse` and `Optional.orElse` provide intentional default values; conversely, `requiredQuantity` actively rejects null while accepting 0.

## 11. How to pinpoint the line of code causing an NPE

When encountering an NPE, review **wrapper sources** and **primitive contexts**:

1. Can the variable's source be null? Parameters, `map.get` results, DTO fields, new wrapper arrays, database results?
2. Does the failing line contain a wrapper-to-primitive assignment, arithmetic operator, `++`/`--`, `+=`, wrapper-to-integer comparison, or mixed ternary operator?
3. If there is `.intValue()`, `.longValue()`, `.doubleValue()`, or `Integer::intValue`, can the receiver be null?
4. Was the wrapper just retrieved from a collection? Is null a valid state for that mapping?
5. Is the NPE really caused by unboxing, or by calling a method like `x.equals(...)` on a null receiver?
6. Should you report a required-field missing error, preserve the null state, or choose a default value?
7. Can you validate and convert to primitives **once at the system boundary** to eliminate null from downstream computation?

With modern JVMs, the NPE message may identify the dereferenced variable or operation, but **you should not write tests depending on the NPE message string**: wording can change across JVM versions, compilation modes, and bytecode structure. Check the exception type and business outcome instead.

### Do not “fix” it with try/catch NullPointerException around every calculation

Catching NPE across an entire pipeline as a normal data-processing path often hides bugs in other objects. Check for null at the source or convert intentionally before computing. Only use `try/catch` when there is genuinely an appropriate exception-handling boundary and the exact cause can be identified.

## 12. Common mistakes

| Misconception | Why is it wrong? | How to handle |
| --- | --- | --- |
| `Integer x = null; int n = x;` automatically takes 0 | Unboxing null throws NPE | Define null as error, optional, or default |
| Only `intValue()` causes NPE | Java automatically unboxes in operators and method calls | Check contexts requiring primitives |
| `Integer x=null; x++` initializes it to 1 | `++` must unbox the old value first | Initialize/validate before updating |
| `Integer x=null; x == 0` is false | Comparing against a primitive forces unboxing | `x != null && x == 0` or validation |
| Two `Integer`s compared with `==` compares values | Compares references and involves caching | `Objects.equals` or unbox after validation |
| `x.equals(y)` is safe when x is null | Calling a method on null throws NPE | `Objects.equals(x,y)` |
| `Integer result = condition ? x : 0` definitely preserves null | The expression type can be primitive `int` | Set explicit common branches/types |
| `Map.getOrDefault` replaces every null with default | Mapping key→null differs from absent key | Check `containsKey` or normalize per contract |
| `Integer[]` defaults to containing 0s | Elements default to null | Initialize elements or use `int[]` |
| `Stream<Integer>.mapToInt` automatically skips null | Converting a null element via `intValue` throws NPE | Filter/validate intentionally |
| Replacing all nulls with 0 is a universal fix | Loses distinction between “missing” and “zero” | Design clear data domains |
| `Objects.requireNonNull` supplies a default value | It throws NPE on null | Use `requireNonNullElse` if a default is appropriate |
| Mistaking NPE for ArithmeticException | Unboxing null is a reference error | Distinguish NPE, domain errors, and division by zero |

## 13. Self-check exercises

1. **Assignment and arithmetic.** Predict the result of `Integer value=null; int a=value;` and `int b=value+1;`. Why do both compile yet throw NPE?
2. **Comparing wrappers.** Given `Integer a=null,b=null;`, predict `a==b`, `a==0`, `Objects.equals(a,b)`, and `a.equals(b)`. In each case, identify whether unboxing occurs.
3. **Ternary operator.** Analyze `Integer x=null; int y=flag?x:0;` with `flag=true` and `flag=false`. If null must be preserved, rewrite the result type and branches appropriately.
4. **Map.** A `HashMap<String,Integer>` contains the mapping `"a" → null` but has no key `"b"`. What does `getOrDefault` return? When unboxing directly, which case throws NPE?
5. **Arrays.** Why does `Integer[] a=new Integer[3]` easily throw NPE when summing, whereas `int[] b=new int[3]` does not? When does using default 0 mask unentered data?
6. **Streams.** Write a pipeline summing non-null elements; explain why the decision to filter out null must come from business requirements.
7. **API design.** An order request has an optional `quantity`. Choose one of three contracts: missing is an error, missing is 0, or missing has its own meaning. Write a function converting the DTO into a validated model.
8. **Boundary tests.** Create unit tests for `requiredQuantity(null)`, `requiredQuantity(0)`, `requiredQuantity(5)`, and negative numbers. Is NPE the best error type to return from the API layer?

## 14. Pre-production checklist

- Treat `Integer`/`Long`/`Double` as **nullable references**, not primitives.
- Clearly identify where Java automatically unboxes: assignment to primitives, primitive parameters, arithmetic operators, `++`/`--`, comparisons with primitives, mixed ternary operators, wrapper maps/streams/arrays.
- Before unboxing, **check for null or convert to an intentional default value**.
- Do not use `==` between two wrappers to check numeric values; do not call `equals` on a potentially null receiver.
- Distinguish **absent key**, **null mapping**, and **value 0** when reading a `Map`.
- Do not assume a newly allocated wrapper array has 0 elements.
- If input is required, validate early and consider converting to primitives for internal computation.
- If data is optional, keep wrappers/`Optional` or an explicit domain state instead of silently turning null into 0.
- Write tests for null, 0, valid values, out-of-range values, and conversion paths into primitives.
- Only catch NPE when a handling boundary truly makes sense; prefer fixing where null data originates.

**Conclusion:** `NullPointerException` during unboxing happens not because an arithmetic operation is wrong, but because Java needs to extract a primitive value from **a wrapper that is currently null**. The sustainable prevention is to clarify missing-data semantics, validate at boundaries, and only unbox after being certain a value exists.
