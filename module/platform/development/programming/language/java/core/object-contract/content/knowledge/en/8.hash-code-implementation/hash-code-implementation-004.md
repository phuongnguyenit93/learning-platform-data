# Using Wrapper Class `hashCode()` Methods for Primitive Types

## 1. Objectives

When implementing `hashCode()` yourself for a Java class, you need to convert each field participating in the equality relation into an `int` hash value, then combine those values using a stable rule. For fields of primitive types (`primitive`), Java directly provides **static** `hashCode(primitive)` methods on the corresponding wrapper classes, such as `Integer.hashCode(int)` or `Double.hashCode(double)`.

After this lesson, you should:

- Know all eight primitive–wrapper pairs; call the right static method without manual boxing.
- Understand why each type's `hashCode` result can differ from a raw cast to `int`, especially for `long`, `float`, and `double`.
- Implement `equals()` and `hashCode()` consistently when a class has multiple primitive fields.
- Avoid confusing the hash of **a single value**, the combined hash of **a multi-field object**, and object identity.
- Know how to handle `NaN`, `+0.0`, and `-0.0` so you do not break the `equals`/`hashCode` contract.

## 2. Static Methods of the Eight Wrapper Classes

All classes below are in `java.lang` and require no `import`. Each method takes a primitive directly and returns an `int`:

| Primitive type | Wrapper class | How to get the hash from a primitive | Key rule |
| --- | --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.hashCode(value)` | `true → 1231`, `false → 1237`. |
| `byte` | `Byte` | `Byte.hashCode(value)` | Returns the `byte` numeric value as an `int`. |
| `short` | `Short` | `Short.hashCode(value)` | Returns the `short` numeric value as an `int`. |
| `char` | `Character` | `Character.hashCode(value)` | Returns the numeric code of the `char` UTF-16 code unit. |
| `int` | `Integer` | `Integer.hashCode(value)` | Returns the `int` value itself. |
| `long` | `Long` | `Long.hashCode(value)` | Mixes the high 32 bits and low 32 bits. |
| `float` | `Float` | `Float.hashCode(value)` | Based on `Float.floatToIntBits(value)`. |
| `double` | `Double` | `Double.hashCode(value)` | Based on the bits of `Double.doubleToLongBits(value)`, then mixes both 32-bit halves. |

Direct call examples:

```java
int ageHash = Integer.hashCode(25);
int enabledHash = Boolean.hashCode(true);
int idHash = Long.hashCode(5_000_000_000L);
int ratioHash = Float.hashCode(1.5f);
int amountHash = Double.hashCode(1.5);
```

This is an illustrative snippet, not a standalone program. The static `hashCode(primitive)` methods have existed since Java 8, so they work in Java 17+.

### Static `hashCode(primitive)` vs. Instance `hashCode()`

Wrapper classes also have an **instance** `hashCode()` method:

```java
int a = Integer.hashCode(42);        // static: int parameter
int b = Integer.valueOf(42).hashCode(); // instance: Integer object
// a == b
```

Both approaches produce the same result for the corresponding value. However, when the source data is already a primitive, prefer the static call: it expresses intent clearly, requires no wrapper variable, and avoids boxing just to call an instance method. Do not claim that every autoboxing operation necessarily allocates an object: the JVM may use caching or optimizations.

A wrapper reference variable can be `null`; calling `wrapper.hashCode()` directly when `null` throws a `NullPointerException`. A primitive can never be `null`, so `Integer.hashCode(int)` never runs into that case.

## 3. Understanding How Each Type Group Works

### 3.1. `boolean`, `byte`, `short`, `char`, and `int`

`Boolean.hashCode(true)` returns `1231`; `Boolean.hashCode(false)` returns `1237`. These are Java-defined constants, **not** `1` and `0`.

`Byte.hashCode(byte)` and `Short.hashCode(short)` return the numeric value converted to `int`. For negative values, the negative sign is preserved. `Character.hashCode(char)` returns the numeric code of a `char` (`0–65535`), which is **one UTF-16 code unit**, not necessarily representing a full Unicode character outside the Basic Multilingual Plane. `Integer.hashCode(int)` returns the exact input `int` value.

Examples:

```java
Boolean.hashCode(true);          // 1231
Boolean.hashCode(false);         // 1237
Byte.hashCode((byte) -5);        // -5
Short.hashCode((short) 300);     // 300
Character.hashCode('A');        // 65
Integer.hashCode(42);           // 42
```

These numbers are the hash values of individual primitives; **they are not guaranteed to be distinct across all inputs or across different data types**. Composite objects must combine hashes across the fields that make up their value.

### 3.2. `long`: Do Not Cast and Drop the High 32 Bits

A `long` has 64 bits, while `hashCode()` must return a 32-bit `int`. The standard formula for `Long.hashCode(long value)` is equivalent to:

```java
(int) (value ^ (value >>> 32))
```

This is an illustrative expression: XOR the high 32 bits with the low 32 bits, then take the resulting 32 bits. When you cast directly with `(int) value`, the high 32 bits are discarded; thus two `long` values that differ only in their upper bits can collide unnecessarily.

Example:

```java
long id = 0x1_0000_0002L;
int lowOnly = (int) id;       // 2
int mixed = Long.hashCode(id); // 3: 1 XOR 2
```

`Long.hashCode` can still experience collisions, because you cannot map all 64-bit values into a 32-bit domain without overlaps. The goal is a deterministic, contract-compliant hash result, not a unique identifier.

### 3.3. `float` and `double`: Use Canonical Floating-Point Bits

Do not use `(int) someFloat` or `(int) someDouble` as a default approach. Casting a floating-point number to `int` converts the numeric magnitude, drops the fractional part, and loses important distinctions preserved by the wrapper contract.

Semantically, the computations are:

```java
int floatHash = Float.floatToIntBits(valueFloat);

// Behavior equivalent to Double.hashCode(valueDouble):
long bits = Double.doubleToLongBits(valueDouble);
int doubleHash = (int) (bits ^ (bits >>> 32));
```

This is a formula illustration; assume `valueFloat` and `valueDouble` are already declared with the appropriate types.

`Float.floatToIntBits` and `Double.doubleToLongBits` **collapse different NaN bit representations into a single canonical NaN bit pattern** for comparison/hashing purposes. They still distinguish the sign of zero:

- `Float.hashCode(+0.0f)` differs from `Float.hashCode(-0.0f)`.
- `Double.hashCode(+0.0)` differs from `Double.hashCode(-0.0)`.
- Different NaN payloads are normalized to the same bit pattern, so they share the same hash under the corresponding wrapper method.

This point is especially important when writing `equals()`:

- The primitive operator `0.0 == -0.0` is `true`; `Double.compare(0.0, -0.0)` **is non-zero**.
- The primitive operator `Double.NaN == Double.NaN` is `false`; `Double.compare(Double.NaN, Double.NaN)` is `0`.
- If a class's `equals()` uses `==` to compare a `double` field while `hashCode()` uses `Double.hashCode`, two objects holding `+0.0` and `-0.0` could be treated as equal by `equals` yet have different hashes, **violating the contract**.

When wrapper semantics are intended, compare `double` with `Double.compare(a, b) == 0` and `float` with `Float.compare(a, b) == 0`, together with `Double.hashCode`/`Float.hashCode`. If the problem requires a different equality relation (such as treating `+0.0` and `-0.0` as equal), **normalize consistently in both `equals` and `hashCode`**. Do not use an `epsilon` tolerance comparison for `equals` because ordinary "nearly equal" relations may fail transitivity.

## 4. From Individual Field Hashes to an Object Hash

A class with multiple fields needs to build a composite hash. A common pattern:

```java
int result = 1;
result = 31 * result + Integer.hashCode(count);
result = 31 * result + Long.hashCode(id);
result = 31 * result + Boolean.hashCode(active);
```

`31` is a common multiplier in Java, **not a mandatory requirement of the contract**. `int` multiplication/addition may overflow; Java performs `int` overflow under 32-bit wrap-around rules, which is normal in hashing. You must keep the **exact same order and same set of fields** on every computation.

More important than any specific formula is the `Object.hashCode()` contract:

> If `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` must be `true`.

The converse is not required: two unequal objects can still share a hash. Nor does a hash prove that two objects are the same reference.

The fields used to compare in `equals` must correspond to the fields used to compute `hashCode`. Do not include transient fields, access counts, object addresses, or changing timestamps in the hash when they are not part of the equality value. For objects used as `HashMap` keys or `HashSet` elements, avoid mutating state that affects the hash after adding them to the collection.

## 5. Complete Java 17+ Program

Create the file `WrapperHashCodeDemo.java`. The example invokes all eight wrappers and implements `equals`/`hashCode` for a value object with primitive fields:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperHashCodeDemo {

    static final class ReadingKey {
        private final long deviceId;
        private final int sequence;
        private final boolean valid;
        private final double reading;

        ReadingKey(long deviceId, int sequence,
                   boolean valid, double reading) {
            this.deviceId = deviceId;
            this.sequence = sequence;
            this.valid = valid;
            this.reading = reading;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ReadingKey other)) {
                return false;
            }

            return deviceId == other.deviceId
                    && sequence == other.sequence
                    && valid == other.valid
                    && Double.compare(reading, other.reading) == 0;
        }

        @Override
        public int hashCode() {
            int result = Long.hashCode(deviceId);
            result = 31 * result + Integer.hashCode(sequence);
            result = 31 * result + Boolean.hashCode(valid);
            result = 31 * result + Double.hashCode(reading);
            return result;
        }
    }

    public static void main(String[] args) {
        System.out.println("boolean: " + Boolean.hashCode(true));
        System.out.println("byte: " + Byte.hashCode((byte) 7));
        System.out.println("short: " + Short.hashCode((short) 300));
        System.out.println("char: " + Character.hashCode('A'));
        System.out.println("int: " + Integer.hashCode(42));
        System.out.println("long: "
                + Long.hashCode(0x1_0000_0002L));
        System.out.println("float: " + Float.hashCode(1.5f));
        System.out.println("double: " + Double.hashCode(1.5));

        ReadingKey a = new ReadingKey(100L, 2, true, 1.5);
        ReadingKey b = new ReadingKey(100L, 2, true, 1.5);
        Set<ReadingKey> keys = new HashSet<>();
        keys.add(a);

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("set contains b: " + keys.contains(b));

        System.out.println("primitive zeros equal: "
                + (0.0 == -0.0));
        System.out.println("double zero hashes equal: "
                + (Double.hashCode(0.0)
                        == Double.hashCode(-0.0)));

        double otherNaN =
                Double.longBitsToDouble(0x7ff0000000000001L);
        System.out.println("NaNs compare equal: "
                + (Double.compare(Double.NaN, otherNaN) == 0));
        System.out.println("NaN hashes equal: "
                + (Double.hashCode(Double.NaN)
                        == Double.hashCode(otherNaN)));

        System.out.println("Objects.hash(42): "
                + Objects.hash(42));
    }
}
```

Compile and run:

```bash
javac WrapperHashCodeDemo.java
java WrapperHashCodeDemo
```

Expected output on Java 17+:

```text
boolean: 1231
byte: 7
short: 300
char: 65
int: 42
long: 3
float: 1069547520
double: 1073217536
a == b: false
a.equals(b): true
same hash: true
set contains b: true
primitive zeros equal: true
double zero hashes equal: false
NaNs compare equal: true
NaN hashes equal: true
Objects.hash(42): 73
```

### Explaining the Output

1. `Boolean` uses two hash constants; `Byte`/`Short`/`Character`/`Integer` reflect the numeric value according to each type's rule.
2. `Long.hashCode(0x1_0000_0002L)` mixes the high part `1` and the low part `2` into `3`.
3. `Float.hashCode(1.5f)` and `Double.hashCode(1.5)` are based on the canonical floating-point bit patterns, not casting `1.5` to the integer `1`.
4. `a` and `b` are two objects with different identities (`==` is `false`), but every field participating in `equals` matches, so `a.equals(b)` is `true` and their hashes are equal.
5. Because hash and equality match, `HashSet` finds `b` even though only `a` was added.
6. Primitive `0.0 == -0.0` is true, whereas the wrapper hash distinguishes the sign of zero. Likewise, `Double.compare` and `Double.hashCode` both treat all NaNs as equivalent under the canonical bit rule.
7. `Objects.hash(42)` returns `73`, unlike `Integer.hashCode(42) == 42`, because it is a **combining hash function over an argument list**, even with a single element: with one argument, array hashing starts at `1`, multiplies by `31`, and adds the element's hash.

## 6. Comparison with `Objects.hash` and `Objects.hashCode`

Three APIs are easily confused:

| Call | Meaning | Note |
| --- | --- | --- |
| `Integer.hashCode(value)` | Directly hashes an `int` | Clear, requires no wrapper variable. |
| `Objects.hashCode(object)` | Calls the hash of **a single object**, returning `0` if `null` | Passing a primitive requires boxing into an `Object`. |
| `Objects.hash(a, b, ...)` | Combines the hashes of multiple objects in an argument list | Uses varargs/array, primitives must be boxed; a single-element result can still differ from that element's own hash. |

Example:

```java
Integer.valueOf(42).hashCode(); // 42
Integer.hashCode(42);           // 42
Objects.hashCode(42);           // 42 (boxing)
Objects.hash(42);               // 73 (one element in an array)
Objects.hash(10, true, 1.5);    // combined hash of the values
```

This snippet requires `import java.util.Objects;`.

`Objects.hash(...)` is convenient for writing concise code, but it allocates a varargs array and may box primitives; for very frequently computed hashes or strict performance requirements, explicitly combining static wrapper methods can reduce intermediate objects. The JVM may optimize allocations, so **benchmark on a realistic workload** before drawing conclusions about actual performance differences.

`Arrays.hashCode(primitiveArray)` is a separate API for computing the hash over the **elements of an array**. Do not use `array.hashCode()` if the class's `equals()` compares array contents: arrays inherit `Object`'s identity-based hashing. In that case, `Arrays.equals(a, b)` usually needs to be paired with `Arrays.hashCode(a)` (nested arrays have dedicated `deepEquals`/`deepHashCode` APIs).

## 7. Mistakes to Avoid

### Mistake 1: Casting `long` down to `int`

```java
// Easily loses the influence of the high 32 bits:
int hash = (int) orderId;

// Includes both high and low parts:
int hash = Long.hashCode(orderId);
```

### Mistake 2: Casting `float` or `double` down to `int`

```java
// Loses the fractional part and many floating-point distinctions:
int hash = (int) temperature;

// Wrapper behavior:
int hash = Double.hashCode(temperature);
```

### Mistake 3: `equals` compares floats with `==`, while `hashCode` uses the wrapper

```java
// Inconsistent when data contains +0.0 and -0.0:
return this.value == other.value;

// If hash uses Double.hashCode(value), you can choose:
return Double.compare(this.value, other.value) == 0;
```

The snippets above are only **illustrative lines inside methods of a class with a `double value` field**, not standalone Java programs. You must decide on the desired equality relation first; if two zeros should be treated as equal, instead of using `Double.compare`, normalize both to `+0.0` for both comparison and hashing.

### Mistake 4: Hashing only one field when `equals` checks multiple fields

This may **still not violate** the `equals/hashCode` contract if that hash is invariant for every pair considered equal, though it often increases collisions and degrades collection performance. Consider combining all fields that make up equality. The opposite direction is more dangerous: adding a field to the hash that **does not participate in `equals`** and can differ between two equal objects **violates the contract**.

### Mistake 5: Thinking "different hashes" are required to prove two objects differ

If two hashes **differ**, the two objects cannot be equal under a contract-compliant implementation; however, **equal** hashes do not prove two objects are equal. `HashMap` and `HashSet` still need to check equality where appropriate.

### Mistake 6: Hashing mutable state

If a field participating in `equals/hashCode` is modified after the object enters a `HashSet`, `contains` may fail to find the existing element. Prefer immutable keys with `final` fields and avoid exposing mutable components that affect the hash.

## 8. Checklist for Implementing `hashCode` on Classes with Primitives

1. List the exact fields that determine the class's equality relation.
2. For each primitive field, use the corresponding `Boolean/Byte/Short/Character/Integer/Long/Float/Double.hashCode(value)`.
3. For nullable reference fields, use a null-safe rule such as `Objects.hashCode(field)`; for strings, collections, or arrays, check their own equality contracts.
4. Combine hash values in a stable order, such as multiplying by `31` and adding.
5. Verify that two equal objects **always** have equal hashes, including edge cases: negative numbers, `long` with high bits set, `NaN`, `+0.0`/`-0.0`, and `null` (if permitted).
6. Test inserting a key and looking it up with another key of the same value in `HashSet`/`HashMap`.
7. If hashing lies on a hot performance path, measure before deciding between `Objects.hash` and manual combination.

## 9. Self-Check Questions

**Question 1.** Why should you use `Long.hashCode(id)` instead of `(int) id` for a `long` field?

**Answer:** Because `Long.hashCode` combines both 32-bit halves. Casting to `int` keeps only the low half.

**Question 2.** For `double`, is using `value == other.value` in `equals` and `Double.hashCode(value)` in `hashCode` always safe?

**Answer:** No. Primitive `+0.0 == -0.0` returns `true` while those two values have different wrapper hashes. If choosing wrapper semantics, use `Double.compare(...) == 0` and `Double.hashCode(...)` consistently.

**Question 3.** Are `Integer.hashCode(42)` and `Objects.hash(42)` equal?

**Answer:** No. In this case they are `42` and `73` respectively because `Objects.hash` uses the single-element array hashing algorithm.

**Question 4.** Can multiple unequal objects share the same hash code?

**Answer:** Yes. Collisions are permitted. What is mandatory is that objects considered equal by `equals` must have equal hash codes.

**Question 5.** When a `boolean enabled` field participates in `equals`, what is the direct way to hash it?

**Answer:** `Boolean.hashCode(enabled)`, which returns `1231` if `true` and `1237` if `false`.

**Remember:** The **static `hashCode(primitive)` methods on wrapper classes** convert primitives into `int` following Java's defined rules. Combine them consistently with the fields in `equals()`, taking special care with `long`, `float`, and `double`.