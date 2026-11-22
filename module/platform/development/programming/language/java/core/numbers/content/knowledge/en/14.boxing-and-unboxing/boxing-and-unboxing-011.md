# Distinguishing a null Reference from the Numeric Value 0 in Java

## 1. The problem: “no value” differs from “value equals 0”

In Java, `null` and the number `0` denote two different states:

- **`null`**: a reference-type variable currently points to no object. This may indicate data not yet provided, unknown, not applicable, or an initialization error, depending on the application's contract.
- **`0`**: an actual numeric value, typically meaning a count of zero, a balance of zero, an arithmetic result of zero, or a status code with value 0.

With primitive `int`, `null` cannot be assigned. With wrapper `Integer`, a variable can reference an object holding the value 0 **or** hold `null`.

~~~java
int primitiveZero = 0;
Integer boxedZero = Integer.valueOf(0);
Integer missing = null;

System.out.println(primitiveZero); // 0
System.out.println(boxedZero);     // 0
System.out.println(missing);       // null
~~~

These three lines are an example placed inside a method. When printed with `System.out.println(Object)`, a null reference outputs the text `null`; that does not mean there is a special `Integer` object carrying a numeric value “null”.

The goal of this lesson is to pick the right model for potentially missing data, recognize every place Java **auto-unboxes**, and avoid accidentally collapsing “unknown quantity” into “quantity definitely equals 0”.

## 2. Primitives and wrappers: two different value domains

| Type | Numeric value 0 | Can hold null? | Use when |
| --- | --- | --- | --- |
| `int` | `0` | No | Always has a valid 32-bit integer |
| `long` | `0L` | No | Always has a valid 64-bit integer |
| `double` | `0.0` | No | Always has a floating-point number, including ±0.0 |
| `Integer` | `Integer.valueOf(0)` | Yes | Must distinguish 0 from a missing integer |
| `Long` | `Long.valueOf(0L)` | Yes | Must distinguish 0 from a missing long integer |
| `Double` | `Double.valueOf(0.0)` | Yes | Must distinguish 0 from a missing floating-point number |

`Integer`, `Long`, `Double`, `Short`, `Byte`, and `Float` are wrapper classes for their corresponding numeric primitives. `Character` and `Boolean` are also primitive wrappers, though not subclasses of `Number`.

~~~java
// int n = null; // Does not compile: null cannot be converted to int.
Integer n = null; // Valid: Integer is a reference type.
Integer z = 0;    // Valid: autoboxing from int 0 to Integer.
~~~

A wrapper object is immutable: `Integer.valueOf(0)` represents the value 0, and the object's contents cannot be changed to 1. However, a non-`final` reference variable can be reassigned to another object or `null`.

### Default values of fields and array elements

Java assigns default `0` to **`int` primitive fields**, yet `null` to **`Integer` fields**:

~~~java
class Defaults {
    int primitiveCount;
    Integer optionalCount;
}

// Inside a method:
Defaults value = new Defaults();
System.out.println(value.primitiveCount); // 0
System.out.println(value.optionalCount);  // null
~~~

Similarly, `new int[3]` has elements equal to 0; `new Integer[3]` has elements equal to `null`. Unassigned local variables cannot automatically be read with default values: the compiler requires variables to be definitely assigned (*definite assignment*) before use.

This matters for DTOs, entities, and input models: choosing `int` can forfeit the ability to represent “not provided”; choosing `Integer` forces code receiving the data to decide how to handle `null`.

## 3. Boxing and unboxing can mask the null/0 difference

**Boxing** converts a primitive value to a wrapper:

~~~java
int raw = 0;
Integer boxed = raw; // autoboxing, boxed value is 0
~~~

**Unboxing** converts a wrapper back to a primitive:

~~~java
Integer boxed = Integer.valueOf(0);
int raw = boxed; // unboxing, raw is 0
~~~

When the wrapper is non-`null`, unboxing retrieves the primitive value. If the wrapper is `null`, Java **throws `NullPointerException`** because there is no object from which to read an inner value.

~~~java
Integer count = null;

// The following statement compiles but throws NullPointerException at runtime:
// int primitive = count;
~~~

That conversion can happen **implicitly**, even when source code does not write `intValue()`:

~~~java
Integer count = null;

// Each expression below requires unboxing count and will throw NPE at runtime:
// int next = count + 1;
// boolean positive = count > 0;
// boolean equalsZero = count == 0;
// int multiplied = count * 2;
~~~

Distinguish unboxing errors from the case where the value is 0: with `Integer count = 0;`, the expressions above are valid and compute properly as integers; with `count = null;`, Java does not treat null as 0 to keep computing.

### Checking null before using the value

~~~java
Integer count = null;

if (count == null) {
    System.out.println("No quantity yet");
} else if (count == 0) {
    System.out.println("Quantity is 0");
} else {
    System.out.println("Quantity is " + count);
}
~~~

The snippet above prints `No quantity yet`. Inside the branch after `else`, we know for certain `count` is non-`null`, so the expression `count == 0` can unbox safely.

## 4. The == operator: reference check or numeric comparison?

The semantics of `==` depend on **the static types of both operands**.

### Two Integer references

~~~java
Integer a = null;
Integer b = null;
Integer zero = Integer.valueOf(0);

System.out.println(a == b);    // true: both are null
System.out.println(a == zero); // false: null differs from an object reference
~~~

When both operands are wrapper references, `==` checks **reference identity**, requiring no unboxing to compare values.

Another example:

~~~java
Integer left = Integer.valueOf(1_000);
Integer right = Integer.valueOf(1_000);

System.out.println(left.equals(right)); // true
// Do not use left == right to determine whether two numeric values are equal.
~~~

`Integer.valueOf` guarantees caching at least values from −128 to 127, and may cache other values. Thus the result of `==` between two wrappers with equal values is not a stable numeric comparison.

### One wrapper and one primitive

~~~java
Integer zero = 0;
System.out.println(zero == 0); // true: Integer is unboxed to int
~~~

Conversely:

~~~java
Integer missing = null;
// System.out.println(missing == 0); // Runtime NPE: unboxes null.
~~~

Therefore `missing == null` is a safe reference check, whereas `missing == 0` is a numeric comparison requiring unboxing and is **not** safe if the reference can be null.

**Precedence order in conditions:**

~~~java
Integer count = null;
boolean isKnownZero = count != null && count == 0;
System.out.println(isKnownZero); // false
~~~

`&&` uses short-circuit evaluation: when `count != null` is `false`, the second side does not execute. This is a safe conditional pattern to check “a number is present and equals 0”.

## 5. equals() and Objects.equals(): safe value-based comparison

`Integer.equals()` compares values **between two Integer objects**, while `java.util.Objects.equals(a, b)` is a convenient way to handle null cases too:

~~~java
Integer missing = null;
Integer zero = Integer.valueOf(0);
Integer anotherZero = Integer.valueOf(0);

System.out.println(java.util.Objects.equals(missing, zero)); // false
System.out.println(java.util.Objects.equals(zero, anotherZero)); // true
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

The `true` result of `Objects.equals(null, null)` only states that **both references are missing** under the null-safe comparison definition; not that they equal 0.

Notes:

- `missing.equals(zero)` throws `NullPointerException` because a method is called on null.
- `zero.equals(missing)` returns `false`; the receiver `zero` is non-null.
- `Objects.equals(missing, zero)` safely returns `false`.
- `Integer.valueOf(0).equals(Long.valueOf(0L))` returns `false` because the two wrappers belong to different classes despite both having mathematical value 0.

When comparing potentially null values from two sources, `Objects.equals` is usually clearer than `==`. However, if logic must distinguish “both missing” from “both equal to 0”, check null separately before performing business comparisons.

## 6. Three common states in application data

You may need to distinguish **three cases** instead of just two:

| State | Example | Possible meaning |
| --- | --- | --- |
| Field/key absent | JSON request omits `count`; `Map` lacks key | Client did not request updating the field |
| Field present with null value | `{"count": null}`; `map.put("count", null)` | Client wants to clear the value or data is unknown |
| Field present with value 0 | `{"count": 0}`; `map.put("count", 0)` | Client asserts the quantity is 0 |

Interpretation depends on the **API contract**. For HTTP PATCH, omitting a field can mean “leave unchanged”, whereas sending `null` can mean “clear”; for HTTP POST, the two cases may be handled differently by validation. This is API design, not a fixed rule of every JSON library.

A single `Integer count` variable alone can only represent **null or a number**; it cannot separately store “field absent” versus “field present and null”. To fully distinguish all three states, you need presence metadata, a structure supporting `containsKey`, or a data type explicitly designed for update requests.

### Map.get() cannot distinguish an absent key from a null mapping

~~~java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
counts.put("explicitNull", null);
counts.put("zero", 0);

System.out.println(counts.get("absent"));       // null
System.out.println(counts.get("explicitNull")); // null
System.out.println(counts.get("zero"));         // 0
~~~

The first two `get` calls both return `null`, yet their meanings differ. Use `containsKey` to determine whether the key exists:

~~~java
System.out.println(counts.containsKey("absent"));       // false
System.out.println(counts.containsKey("explicitNull")); // true
System.out.println(counts.containsKey("zero"));         // true
~~~

With `HashMap`, `getOrDefault` only uses the default value when **there is no mapping for the key**; if the key exists and maps to null, the result is still null:

~~~java
System.out.println(counts.getOrDefault("absent", -1));       // -1
System.out.println(counts.getOrDefault("explicitNull", -1)); // null
~~~

Do not use `map.getOrDefault(key, 0)` as a blanket solution to turn every null into 0. It does not handle keys mapped to null, and automatically turning missing data into 0 can violate the business contract.

## 7. Choosing a clear model for “number not provided”

### Case 1: Value must always exist

Use a primitive like `int` and validate at the data-ingestion boundary. When quantity can be 0 yet must never be missing, representing it with a primitive makes sense once input has been validated.

~~~java
static int requireCount(Integer count) {
    if (count == null) {
        throw new IllegalArgumentException("count is required");
    }
    if (count < 0) {
        throw new IllegalArgumentException("count cannot be negative");
    }
    return count;
}
~~~

This is a **Java method** to place inside a class, not a standalone runnable program. The `count < 0` branch runs only after checking null, so unboxing is safe. If inputs must allow negative numbers, omit that check per business rules.

### Case 2: Value may be unknown

Use `Integer` together with an explicit null-handling branch:

~~~java
static String describe(Integer count) {
    if (count == null) return "unknown";
    if (count == 0) return "none";
    return "count=" + count;
}
~~~

This method distinguishes “unknown” from “known to be 0”. Do not write `count == null ? 0 : count` if you still need to preserve the distinction.

### Case 3: Expressing missing values via a dedicated API

`java.util.OptionalInt` can describe “has an integer” or “has no integer”:

~~~java
java.util.OptionalInt absent = java.util.OptionalInt.empty();
java.util.OptionalInt presentZero = java.util.OptionalInt.of(0);

System.out.println(absent.isPresent()); // false
System.out.println(presentZero.isPresent()); // true
System.out.println(presentZero.getAsInt()); // 0
~~~

`OptionalInt` eliminates the need to use null for the optional value itself and avoids the boxing of `Optional<Integer>`. However, `absent.orElse(0)` **intentionally collapses** the missing value into 0 when extracting the result; only do so if business logic permits.

`OptionalInt` fits expressing presence/absence results in certain APIs. For entity fields, JSON data types, ORMs, or serialization libraries, pick a representation clearly supported by the framework and test actual mappings; do not assume every tool serializes Optional identically.

## 8. Ternaries, conditions, and methods: hidden unboxing

The conditional operator `condition ? a : b` has rules determining the result type from **the branch types**. When mixing a wrapper with a numeric primitive of the same kind, Java can choose the primitive type and unbox the wrapper **only in the selected branch**:

~~~java
Integer missing = null;
boolean useMissing = true;

// This snippet throws NullPointerException at runtime:
int result = useMissing ? missing : 0;
~~~

There is no way to force Java to implicitly interpret `missing` as 0. If the result must retain nullability, intentionally use an expression with a reference type and clear contract. For example:

~~~java
Integer missing = null;
boolean useMissing = true;
Integer selected = useMissing ? missing : Integer.valueOf(0);
System.out.println(selected); // null
~~~

Also be careful with methods taking primitives:

~~~java
static void printCount(int value) {
    System.out.println(value);
}

// Integer count = null;
// printCount(count); // NPE when trying to unbox before calling the method.
~~~

When defining an API accepting `Integer` or returning `Integer`, authors and callers must understand whether `null` is a valid state or a contract violation. If a method **always** returns a valid number, a primitive return type eliminates the possibility of returning null; if the value can be absent, document it clearly and consider Optional or a state-expressing result type.

## 9. Distinguishing null and 0 in JDBC and databases

In SQL, `NULL` marks missing/unknown values in the database model; `0` is a numeric value. For a nullable column, the two cases usually need to be preserved separately.

Specifically, `java.sql.ResultSet.getInt("quantity")` **returns 0 for SQL NULL** under the JDBC contract. To distinguish them, call `wasNull()` immediately after the corresponding getter:

~~~java
// Illustrative snippet inside code that already has java.sql.ResultSet rs:
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
~~~

You must call `wasNull()` **immediately after reading that column**, because it reflects the NULL status of the most recently read column by a getter. If other getters are called beforehand, the flag may no longer correspond to `quantity`.

Some drivers/JDBC APIs support object retrieval like `getObject(..., Integer.class)`, which can return null for SQL NULL when supported. Check the documentation and behavior of the specific driver, especially when mapping to DTOs/ORMs.

**Business lesson:** if “no inventory quantity reported” and “inventory equals 0” are two distinct states, mapping SQL NULL straight into primitive `int` or calling `getInt` while ignoring `wasNull()` can silently lose critical data.

## 10. JSON, forms, and default values

When receiving data from JSON or forms, define each case clearly:

- Field absent: apply a default, reject, or keep the previous value?
- Field is `null`: is it valid? Does it mean “clear value”?
- Field is `0`: is it a valid value or does it violate a minimum bound?
- Field is the string `"0"`: is string-to-number coercion permitted?
- Field is the string `"null"`: that is a four-character string, not Java `null` or JSON `null`.

Frameworks can differ in deserialization, coercion, validation, and default rules. Do not blindly assume Jackson, Gson, Spring Data Binding, or another library automatically preserves all three states when mapping every field onto a plain `Integer`.

A design example:

| Payload | Assumed update API behavior |
| --- | --- |
| `{}` | Do not change existing quantity |
| `{"quantity": null}` | Clear stored quantity, if permitted |
| `{"quantity": 0}` | Update quantity to 0 |
| `{"quantity": 5}` | Update quantity to 5 |

This is an **example API convention**, not an automatic rule of Java or JSON. To implement it accurately, track field presence and apply validation per contract.

## 11. Complete Java 17+ program

Create file `NullVsZeroDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;

public class NullVsZeroDemo {
    static String describe(Integer count) {
        if (count == null) {
            return "missing";
        }
        if (count == 0) {
            return "zero";
        }
        return "nonzero: " + count;
    }

    public static void main(String[] args) {
        Integer absent = null;
        Integer zero = Integer.valueOf(0);

        System.out.println("absent is null: " + (absent == null));
        System.out.println("zero is null: " + (zero == null));
        System.out.println("absent equals zero: " + Objects.equals(absent, zero));
        System.out.println("zero equals 0: " + Objects.equals(zero, 0));

        System.out.println("describe absent: " + describe(absent));
        System.out.println("describe zero: " + describe(zero));
        System.out.println("describe five: " + describe(5));

        try {
            int primitive = absent; // NPE due to unboxing null
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unboxing absent: NPE");
        }

        Map<String, Integer> counts = new HashMap<>();
        counts.put("explicitNull", null);
        counts.put("zero", 0);

        System.out.println("missing key present: " + counts.containsKey("absent"));
        System.out.println("null key present: " + counts.containsKey("explicitNull"));
        System.out.println("zero key present: " + counts.containsKey("zero"));
        System.out.println("default for absent: " + counts.getOrDefault("absent", -1));
        System.out.println("default for explicit null: " +
                counts.getOrDefault("explicitNull", -1));

        OptionalInt noCount = OptionalInt.empty();
        OptionalInt zeroCount = OptionalInt.of(0);
        System.out.println("optional absent present: " + noCount.isPresent());
        System.out.println("optional zero: " + zeroCount.getAsInt());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 NullVsZeroDemo.java
java NullVsZeroDemo
~~~

Stdout output:

~~~text
absent is null: true
zero is null: false
absent equals zero: false
zero equals 0: true
describe absent: missing
describe zero: zero
describe five: nonzero: 5
unboxing absent: NPE
missing key present: false
null key present: true
zero key present: true
default for absent: -1
default for explicit null: null
optional absent present: false
optional zero: 0
~~~

Explanation:

1. `absent == null` only checks **reference equality**, whereas `zero` points to a valid wrapper holding 0.
2. `Objects.equals(absent, zero)` returns false without throwing NPE; 0 only equals a numeric value 0 with matching semantics.
3. `describe` intentionally preserves three states: missing, zero, and nonzero.
4. Forcing `absent` to `int` fails at runtime, showing unboxing does not replace null with 0.
5. `HashMap.containsKey` distinguishes an absent key from an existing key mapped to null; `getOrDefault` only applies the default for absent keys.
6. `OptionalInt.empty()` and `OptionalInt.of(0)` separate missing values from 0 without needing a null reference inside the optional.

## 12. Other wrapper types share the same issue

### Long, Short, Byte

~~~java
Long absentId = null;
Long idZero = 0L;
System.out.println(absentId == null); // true
System.out.println(idZero.longValue() == 0L); // true
~~~

If you have `Long id = null;`, additions, numeric comparisons, or unboxing to `long` will throw NPE just like `Integer`. Do not use 0 as a “non-existent value” unless the data contract establishes that 0 **cannot be a valid value**.

### Double and Float

~~~java
Double absentMeasurement = null;
Double zeroMeasurement = 0.0;

System.out.println(absentMeasurement == null); // true
System.out.println(zeroMeasurement == null);    // false
~~~

For floating point, there are also `+0.0` and `-0.0`. Both are valid floating-point values, **both distinct from `null`**. Primitive floating-point comparison `+0.0 == -0.0` returns true, whereas `Double.equals()` distinguishes signed zeros. That is a question of **floating-point equality**, separate from checking null references.

`Double.NaN` is also **not null**. NaN represents an undefined floating-point result under IEEE 754; it is still a value inside a `Double` object when boxed. If the application also needs to distinguish “missing measurement”, “NaN from computation”, and “value 0”, define separate rules for each case.

### Boolean: false differs from null

Although not numeric, `Boolean` is a very close illustration:

~~~java
Boolean noResponse = null;
Boolean explicitlyFalse = Boolean.FALSE;

System.out.println(noResponse == null);      // true
System.out.println(Boolean.FALSE.equals(noResponse)); // false
~~~

A field can represent “no response yet”, “answered no”, and “answered yes”. Using primitive `boolean` cannot store the unanswered state as null.

## 13. When is replacing null with 0 acceptable?

Converting a missing value to 0 is not always wrong. It is appropriate when **the business contract specifies** that missing data equals zero. For example, a function totaling optional fees might treat an absent fee as 0.

~~~java
static int orZero(Integer value) {
    return value == null ? 0 : value;
}
~~~

This method erases the difference between null and 0 **intentionally**. That must be an explicit decision at a processing boundary, not a default applied across every layer of the system.

Avoid:

~~~java
// Pattern prone to distorting meaning if "unknown" differs from "equals 0":
// Integer stock = repository.findStock(...);
// int safeStock = stock == null ? 0 : stock;
~~~

If `null` means “not yet inventoried”, the variable `safeStock` can be misinterpreted as “definitely out of stock”. Instead, keep a nullable value, introduce a clear enum status, or return a structured result containing verification status.

**Rule:** only collapse states when you know for sure what semantics consumers of the result expect.

## 14. Common mistakes and how to avoid them

| Practice / habit | Risk | Right way |
| --- | --- | --- |
| `Integer x = null; int y = x;` | NPE on unboxing | Check null or set non-null contract |
| `Integer x = null; x == 0` | NPE on numeric comparison | `x != null && x == 0` |
| `x.equals(0)` when `x` is nullable | NPE if x is null | `Objects.equals(x, 0)` or check null |
| `Integer a, b; a == b` to compare values | Depends on identity/caching | `Objects.equals(a, b)` |
| Treating every null `Integer` as 0 | Loses “unknown” meaning | Apply default only when business rules allow |
| `map.get(key) == null` means key is absent | Fails to distinguish existing key with null mapping | `map.containsKey(key)` |
| `map.getOrDefault(key, 0)` handles all nulls | Key mapped to null still returns null | Define separate policies for absent keys and null values |
| `ResultSet.getInt` suffices for reading nullable SQL integers | SQL NULL also returns 0 | Immediately call `ResultSet.wasNull()` |
| Using primitive fields when needing to know if a JSON field was present | Cannot represent null; loses “absent” info | Track presence and deserialization contract |
| Treating string `"0"` as equal to number 0 before parsing | Different data types | Parse/validate per input format |
| Calling `OptionalInt.orElse(0)` then forgetting the absent state | Intentionally drops missing info | Check `isPresent()` or handle absent branch first |
| Equating `Double.NaN`, `0.0`, and `null` | Three cases with different semantics | Check `null`, `Double.isNaN`, and value 0 separately |

## 15. Self-check questions

**Question 1.** Are these two lines the same?

~~~java
Integer a = null;
Integer b = 0;
~~~

**Answer:** No. `a` points to no object; `b` points to an `Integer` representing 0. `a == null` is true; `b == null` is false.

**Question 2.** Why does `Integer count = null; if (count == 0) ...` throw an error?

**Answer:** The operand `0` is primitive `int`, causing Java to unbox `count` to compare values. Unboxing a null reference causes `NullPointerException`.

**Question 3.** Does `Objects.equals(null, null)` returning true mean null equals 0?

**Answer:** No. It only indicates both arguments are null. `Objects.equals(null, 0)` returns false.

**Question 4.** In a `HashMap`, does `get("x")` returning null prove key x does not exist?

**Answer:** No. The key may exist and be mapped to null. Use `containsKey("x")` to distinguish.

**Question 5.** If a SQL column contains NULL, what does `ResultSet.getInt("quantity")` return and what must you check?

**Answer:** It returns primitive 0. Immediately call `wasNull()` to distinguish SQL NULL from an actual numeric value 0.

**Question 6.** When should you use `Integer` instead of `int`?

**Answer:** When object/generic APIs require it or when expressing a state that may lack a value; if data is guaranteed to hold a number and null representation is unneeded, `int` is usually simpler.

**Question 7.** `OptionalInt.empty().orElse(0)` and `OptionalInt.of(0).orElse(0)` both return 0. Can you still distinguish the input states?

**Answer:** No, because calling `orElse(0)` intentionally converted both to primitive 0. If distinction is needed, use `isPresent()`/handling branches beforehand.

## 16. Takeaways and references

- **`null` signifies no object; `0` signifies a valid value**. This is a data and business distinction, not merely syntax.
- **Primitives cannot hold null; wrappers can hold null**. Auto-unboxing null throws `NullPointerException`.
- **`== null` checks references; `== 0` with a wrapper requires unboxing**. Use null guards or `Objects.equals` in the right context.
- **`Map.get`, JDBC `getInt`, and field deserialization** can lose information if missing states are not handled intentionally.
- Use `OptionalInt` or result structures carrying presence info when API contracts require it. Only convert null to 0 when business logic permits.

Java 17 documentation:

- [Java Language Specification — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) and [Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).
- [Java Language Specification — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).
- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html) and [Objects.equals API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
- [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) and [OptionalInt API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html).
- [JDBC ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `getInt` and `wasNull`.