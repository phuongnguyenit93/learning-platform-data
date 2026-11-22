# Upper and Lower Bounds of a Captured Type (Wildcard Capture) in Java Generics

**Wildcard capture** is a Java compiler mechanism: when encountering a generic type containing `?`, the compiler can replace the unknown type argument with **a temporary, distinct type variable**. That type variable often appears in error messages under names like `CAP#1` or `capture of ? extends Number`. Although we cannot write the name `CAP#1` directly in source code, the compiler still uses its **upper and lower bounds** to decide whether reading, writing, assigning, and calling methods are safe.

Summary for `List<E>`, where `E` declares no special bound (default upper bound is `Object`):

| Wildcard argument | Captured type: upper bound | Lower bound | Read from `get` as what type? | What kind of value can be added? |
| --- | --- | --- | --- | --- |
| `?` | `Object` | `null` type | `Object` | Only the `null` literal at the type-system level |
| `? extends Number` | `Number` | `null` type | `Number` | Only the `null` literal at the type-system level |
| `? super Integer` | `Object` | `Integer` | `Object` | `Integer` and compatible subtypes |
| `? super Number` | `Object` | `Number` | `Object` | `Number` and its subtypes |

The table represents **static guarantees of the type system**; it does not promise that the runtime collection supports modification or accepts `null`. For generics whose type parameter itself declares an upper bound, such as `Box<T extends Number>`, the captured type's upper bound can be `Number` instead of `Object`; this is explained in detail below.

## 1. Why Capture Wildcards?

Consider:

```java
List<? extends Number> numbers = List.of(1, 2);
Number number = numbers.get(0);
```

The list's actual type argument could be `Integer`, `Double`, `Number`, or another subtype of `Number`. The compiler does not know the exact type, yet needs to reason about **a single consistent type** for elements of that same list.

You can imagine the compiler temporarily naming that element type:

```text
List<? extends Number>
          |
          v
List<CAP#1>
  with CAP#1 <: Number
```

The notation `CAP#1` is purely explanatory. There is no valid `class CAP#1` declaration or `List<CAP#1>` syntax in an ordinary Java program.

Because the captured type lies beneath `Number`, the result of `numbers.get(0)` can always be treated as `Number`. However, the compiler cannot assume `CAP#1` is specifically `Integer`:

```java
Number n = numbers.get(0);  // Valid.
// Integer i = numbers.get(0); // Does not compile.
// numbers.add(42);           // Does not compile.
```

If the real list is `List<Double>`, adding an `Integer` would break the element type contract. Wildcard capture lets the compiler preserve type-relationship information without guessing the actual type argument.

## 2. Upper and Lower Bounds of a Captured Type Variable

Intuitively, a captured type variable `CAP` can be constrained from two sides:

```text
UpperBound
     ^
     | CAP <: UpperBound
    CAP
     ^
     | LowerBound <: CAP
LowerBound
```

The notation `A <: B` means `A` is a subtype of `B` under Java's type system. Knowing the upper bound means a value of type `CAP` can be **read out** and treated as the upper bound type. Knowing the lower bound means values of the lower bound type can be **passed in**, because every valid type `CAP` must be a supertype of that lower bound.

The two bounds serve different purposes:

- **Upper bound:** an object of type `CAP` can be widened to this type, determining which APIs can be called when reading.
- **Lower bound:** this type and compatible subtypes can be passed where `CAP` is expected, determining which values can be written.
- **Neither bound determines a fixed runtime class.** Capture is used in compile-time type analysis and creates no new class.

Java also has a special **`null` type**. In the language specification's description of capture rules, this is the lower bound of `?` and `? extends B`. It explains why the `null` literal can be passed where a captured reference type is expected, without promising that the collection accepts it at runtime.

Do not misinterpret “lower bound is the `null` type” as meaning every existing element is `null`, or upper bound `Number` as meaning every value is non-null. Those are two wrong conclusions.

## 3. Capture of `? extends Number`: Strong Upper Bound, Weak Lower Bound

With `List<? extends Number>`:

- `CAP` has **upper bound `Number`** (in this simple case);
- the lower bound is the `null` type;
- the compiler allows reading as `Number`;
- the compiler forbids arbitrarily adding a specific `Integer`, `Double`, or `Number`.

Example:

```java
static void readSource(List<? extends Number> source) {
    for (Number value : source) {
        System.out.println(value);
    }

    // source.add(1);           // Does not compile.
    // source.add(1.5);         // Does not compile.
    // source.add((Number) 3);  // Does not compile.
    source.add(null);           // Type-valid; may fail at runtime.
}
```

In `source.add(1)`, `Integer` is only known to be a subtype of `Number`, not proven to be a subtype of `CAP` itself. The source might be `List<Double>`, making the insertion unsafe.

The `null`-type lower bound explains why `source.add(null)` is accepted by the compiler. However, if `source` is an unmodifiable list from `List.of(...)`, `add(null)` still throws `UnsupportedOperationException`; if the implementation forbids `null`, it may throw `NullPointerException`. Runtime conditions are independent of wildcard capture.

A common example: `? extends Number` is a **producer** in the PECS rule (*Producer Extends, Consumer Super*). It fits when you need to retrieve values as `Number` without adding new `Number` objects through the wildcard reference.

## 4. Capture of `? super Integer`: Strong Lower Bound, Upper Bound Depends on Declaration

With `List<? super Integer>`:

- `CAP` has **lower bound `Integer`**;
- the default upper bound is `Object` because `List<E>`'s parameter `E` has no tighter bound;
- the compiler allows adding `Integer`;
- when reading, the compiler only guarantees receiving `Object`.

Example:

```java
static void writeDestination(List<? super Integer> destination) {
    destination.add(10); // Valid.
    destination.add(20); // Valid.

    // destination.add(2.5); // Does not compile.

    Object value = destination.get(0); // Valid.
    // Integer n = destination.get(0); // Does not compile.
}
```

Reason: `destination` could be `List<Integer>`, `List<Number>`, `List<Object>`, or even `List<java.io.Serializable>`. All of these lists accept `Integer`, yet a `List<Object>` might already contain `String`s. Therefore not every retrieved element can be treated as `Integer` or `Number`.

This forms a two-way mental model to remember:

```text
? extends Number                 ? super Integer
-----------------------          -----------------------
Read:  Number                    Read:  Object
Write: no concrete Number added  Write: Integer
Upper: Number                    Upper: Object (for List<E>)
Lower: null type                 Lower: Integer
```

The upper bound of `? super Integer` **is not always `Object`**, because it also depends on the bound of the type parameter declared in the generic type. That distinction is very important.

## 5. Complete Java 17 Example: Reading/Writing by Capture Bounds

Save as `CaptureBoundsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureBoundsDemo {
    static void fromExtends(List<? extends Number> source) {
        Number first = source.get(0);
        System.out.println("upper read=" + first);

        // source.add(99); // Does not compile: CAP#1 is unknown.
        source.add(null);   // Only valid because null is compatible with CAP#1.
    }

    static void fromSuper(List<? super Integer> destination) {
        destination.add(10);
        Object first = destination.get(0);
        System.out.println("lower read=" + first);

        // Number n = destination.get(0); // Does not compile.
    }

    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2));
        fromExtends(source);
        System.out.println("source=" + source);

        List<Number> destination = new ArrayList<>();
        fromSuper(destination);
        System.out.println("destination=" + destination);
    }
}
```

Commands:

```bash
javac CaptureBoundsDemo.java
java CaptureBoundsDemo
```

Output:

```text
upper read=1
source=[1, 2, null]
lower read=10
destination=[10]
```

The program uses `ArrayList` to ensure adding `null` is supported. With other collections, you cannot deduce runtime behavior from type validity. Both methods also demonstrate that read/write permissions are determined by **the parameter signature**, not by how the list was constructed at the call site.

## 6. Declared Bounds of a Generic Affect the Capture's Upper Bound

This is an important difference between an ordinary `List<E>` and a generic with a declared upper bound.

Consider:

```java
class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Here, type `T` **must be `Number` or a subtype of `Number`**. Consequently, even when using a lower-bounded wildcard, the upper bound of the captured type still cannot be wider than `Number`.

| Type | Upper bound of captured type | Lower bound |
| --- | --- | --- |
| `List<? super Integer>` | `Object` | `Integer` |
| `NumberBox<? super Integer>` | `Number` | `Integer` |
| `NumberBox<?>` | `Number` | `null` type |
| `NumberBox<? extends Integer>` | `Integer` | `null` type |

With `NumberBox<? super Integer>`, we can **read `Number`** and **write `Integer`**. This does not contradict the rule that `List<? super Integer>` only reads `Object`. The difference comes from the upper bound `T extends Number` declared on `NumberBox`.

### Runnable example: capture with both upper `Number` and lower `Integer`

Save as `BoundedBoxCaptureDemo.java`:

```java
public class BoundedBoxCaptureDemo {
    static final class NumberBox<T extends Number> {
        private T value;

        NumberBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    static void useBox(NumberBox<? super Integer> box) {
        Number before = box.get(); // Upper bound is Number.
        box.set(42);               // Lower bound is Integer.
        Number after = box.get();

        System.out.println("before=" + before);
        System.out.println("after=" + after);
    }

    public static void main(String[] args) {
        NumberBox<Number> numbers = new NumberBox<>(2.5);
        useBox(numbers);
        System.out.println("actual=" + numbers.get());

        NumberBox<Integer> integers = new NumberBox<>(7);
        useBox(integers);
        System.out.println("actual=" + integers.get());
    }
}
```

```bash
javac BoundedBoxCaptureDemo.java
java BoundedBoxCaptureDemo
```

Output:

```text
before=2.5
after=42
actual=42
before=7
after=42
actual=42
```

Both `NumberBox<Number>` and `NumberBox<Integer>` match `NumberBox<? super Integer>`. Every accepted type argument of `NumberBox` must be a subtype of `Number`, so reading as `Number` is always safe; every candidate for `? super Integer` accepts `Integer`, so calling `set(42)` is also safe.

Lesson: do not mechanically memorize “`? super` can only read `Object`” for **every** generic. More accurately: values can be read as the **upper bound of the captured variable**; for `List<E>` this bound is usually `Object`, whereas for `NumberBox<T extends Number>` it is `Number`.

## 7. How the Compiler Determines Upper and Lower Bounds

For a generic's declared type parameter `T`, the compiler considers the **declared bound of `T`** first, then combines it with the wildcard at the use site. Three basic cases are worth remembering:

### Case A: unbounded wildcard `?`

- **Upper bound:** the declared upper bound of type parameter `T` (typically `Object`).
- **Lower bound:** the `null` type.

Hence `List<?>` reads `Object`, while `NumberBox<?>` reads `Number`.

### Case B: wildcard `? extends B`

- **Upper bound:** combined from the wildcard's bound `B` and the declared bound of `T`, in language terms the *greatest lower bound* (`glb`) of the constraints to satisfy.
- **Lower bound:** the `null` type.

In the simple case `List<? extends Number>`, the declared bound of `List<E>` is `Object`, so the resulting upper bound is `Number`. With `NumberBox<? extends Integer>`, the upper bound is `Integer` because `Integer` is beneath `Number`.

When the declared bound includes multiple interfaces, the upper bound may be represented as an **intersection type** by the compiler. For example, a class declaring `T extends Number & java.io.Serializable` alongside a wildcard with another upper bound can force `CAP` to satisfy multiple constraints simultaneously. Do not assume the compiler always keeps verbatim only the single type written after `extends`.

### Case C: wildcard `? super B`

- **Upper bound:** the **declared upper bound of `T`**, after substituting related generic parameters.
- **Lower bound:** `B`.

For `List<? super Integer>`, upper is `Object`, lower is `Integer`. For `NumberBox<? super Integer>`, upper is `Number`, lower is `Integer`.

These rules describe the core idea of capture conversion specified in *Java Language Specification*, section 5.1.10. Generics with self-referential bounds or multiple interdependent type parameters can produce more complex bounds after substitution; nevertheless, the principle of reading from the upper bound and passing values compatible with the lower bound remains a useful foundation.

## 8. Distinguishing Wildcard Bounds from Captured Type Bounds

The expression:

```java
List<? super Integer> sink;
```

has a **wildcard explicitly stating lower bound `Integer`**. When captured, the compiler creates a temporary type with bounds on both sides: upper from `List<E>` is `Object`, lower is `Integer`.

Therefore, the phrase “upper and lower bounds of a captured type” refers to **both sides** of the temporary `CAP` type, not merely reading the keyword `extends` or `super` in source code.

An illustrative diagram:

```text
List<? super Integer>      -> CAP#1:
                                  Integer <: CAP#1 <: Object

NumberBox<? super Integer> -> CAP#2:
                                  Integer <: CAP#2 <: Number

List<? extends Number>     -> CAP#3:
                                  null-type <: CAP#3 <: Number

NumberBox<?>               -> CAP#4:
                                  null-type <: CAP#4 <: Number
```

`null-type` here is the type system's representation of the lower bound, not a class name. Each capture can create a distinct type variable; `CAP#1`, `CAP#2` labels in compiler errors are not stable across compilers or compilation sites.

## 9. Two Captures from Two Different Wildcards Are Not Equal

Even when two parameters use the exact same syntax `List<? extends Number>`, the compiler **does not automatically treat their captured element types as the same type**.

Example:

```java
static void moveFirst(
        List<? extends Number> source,
        List<? extends Number> destination) {

    Number value = source.get(0); // Can read Number.

    // destination.add(value); // Does not compile.
}
```

`source` could be `List<Integer>`, while `destination` could be `List<Double>`. The captures of the two wildcards are distinct temporary types. Sharing the upper bound `Number` does not make them equal.

To transfer numbers from a source to a **consumer destination**, declare:

```java
static void append(
        List<? extends Number> source,
        List<? super Number> destination) {
    for (Number value : source) {
        destination.add(value);
    }
}
```

Here upper `Number` lets the source be read as `Number`, and lower `Number` lets the destination accept any `Number`. That is precisely the PECS producer/consumer combination. The destination can be `List<Number>` or `List<Object>`, but cannot be `List<Integer>` if the source might hold `Double`.

If you need a caller-chosen common type, a more general signature is:

```java
static <T> void appendGeneric(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

This approach uses the same `T` to link the producer's upper bound and the consumer's lower bound, while still allowing two different generic arguments.

## 10. A Helper Preserves the Upper Bound When Handling One Captured Type

With `List<? extends Number>`, the compiler knows the hidden element type is a subtype of `Number`, yet forbids writing an arbitrary `Integer`: the real list might be `List<Double>`.

If you need to **repeat an existing element itself**, use a helper with the corresponding bound:

```java
static void repeatFirstNumber(List<? extends Number> source) {
    repeatCapturedNumber(source);
}

private static <E extends Number> void repeatCapturedNumber(List<E> source) {
    if (!source.isEmpty()) {
        E first = source.get(0);
        double numericalValue = first.doubleValue();
        source.add(first);
        System.out.println("repeated=" + numericalValue);
    }
}
```

The methods must be placed inside a class importing `java.util.List`. Calling `repeatCapturedNumber(source)` captures `? extends Number` into an `E` satisfying `E extends Number`. Thus `doubleValue()` is valid **and** the value retrieved from `List<E>` itself can be added back to the same list as `E`.

By contrast, `source.add(42)` directly on `List<? extends Number>` does not compile, and the helper also does not let you fabricate a new `E` from `42`. At runtime, you still have to consider whether the list supports adding elements; `List.of` is unmodifiable. With `? super Integer`, read capability also depends on **the declared type parameter's upper bound**: `List<E>` allows reading `Object`, whereas `NumberBox<E extends Number>` allows reading `Number`.

The focus here is that **the bounds of the captured type determine valid operations**, not swap algorithms or `CAP#` naming in diagnostics.

## 11. Reading/Writing via Upper and Lower Bounds Does Not Mean Automatic Casting

Consider `NumberBox<? super Integer>`: you can read `Number`, write `Integer`. That **does not** mean the compiler automatically converts every read value to `Integer`:

```java
NumberBox<? super Integer> box = new NumberBox<Number>(2.5);
Number read = box.get(); // Valid.
// Integer i = box.get(); // Does not compile.
box.set(3);              // Valid.
// box.set(3.5);          // Does not compile.
```

The snippets in this section rely on the `NumberBox<T extends Number>` declaration from section 6 and serve as signature illustrations, not a standalone Java file.

`box.get()` can return a `Double` because the actual object is `NumberBox<Number>`. An explicit cast to `Integer` could throw `ClassCastException`; do not use casts to erase uncertainty about a captured type.

Conversely, `box.set(3)` is valid because `Integer` can go into any `NumberBox` satisfying `? super Integer` with bound `T extends Number`. The lower bound tells you which values are safe to **put in**, not which values are guaranteed to **come out**.

## 12. Type Erasure and the Scope of Capture

Wildcard capture is an operation of the **static type system**, not a runtime check of generic type arguments. Java generally uses *type erasure* for generics, so at runtime no separate type object named `CAP#1` exists for direct querying.

Example:

```java
List<? extends Number> first = new ArrayList<Integer>();
List<? extends Number> second = new ArrayList<Double>();

System.out.println(first.getClass() == second.getClass());
```

The result is `true` because both runtime objects are `ArrayList`; the difference between `Integer` and `Double` is reflected through the compile-time constraints of each declaration, not through two separate runtime classes `ArrayList<Integer>` and `ArrayList<Double>`.

A complete runnable program for this snippet needs a class containing a `main` method along with `import java.util.List;` and `import java.util.ArrayList;`. The current snippet is only meant to explain erasure.

That also does not permit arbitrarily casting `List<Integer>` to `List<Double>`. The static type system before execution prevents operations that corrupt data consistency. Raw types or unchecked casts can bypass checks, yet they cause delayed type errors and should be avoided.

## 13. Common Pitfalls

### Pitfall 1: assuming `? super T` always reads `Object` regardless of the generic declaration

With `List<? super Integer>`, reading `Object` is the usual guarantee. With `NumberBox<? super Integer>`, however, the declared bound `T extends Number` allows reading as `Number`. You must examine **both the wildcard and the declared type parameter's bound**.

### Pitfall 2: seeing `? extends Number` and assuming the capture is always `Number`

False. The actual type could be `Integer` or `Double`. `CAP <: Number` is only an upper bound, not the equation `CAP = Number`. Therefore you still cannot arbitrarily add a concrete `Number`.

### Pitfall 3: seeing `? super Integer` and assuming every existing element is `Integer`

False. `List<? super Integer>` could be a `List<Object>` already containing strings. The lower bound guarantees `Integer` can be added, not that every element read out is an `Integer`.

### Pitfall 4: thinking wildcards with the same bound share the same capture

Two `List<? extends Number>` sources can contain different subtypes. You cannot copy elements from one source directly into the other based merely on sharing an upper bound.

### Pitfall 5: using `List<Object>` instead of `List<?>` to handle capture

`List<Object>` cannot directly accept `List<String>` because generics are invariant. `List<?>` is the proper signature when an algorithm only reads general values as `Object` and needs no exact element type.

### Pitfall 6: thinking a helper method removes type bounds

A generic helper does not allow adding values of the wrong type. It only names a capture to pass **values of the exact same type `E`** between safe positions. Trying `items.add((E) someObject)` via an unchecked cast still risks type errors.

### Pitfall 7: believing upper bound `Number` forbids `null` values

No. An `ArrayList<Integer>` can hold `null`, and when read through `List<? extends Number>`, the received value can be `null`. A type bound describes a subtype relationship, not a non-null guarantee.

### Pitfall 8: confusing capture errors with runtime data errors

Messages containing `CAP#1` usually mean the compiler could not prove a type relationship at a generic call. `UnsupportedOperationException`, `NullPointerException`, or `ClassCastException` at runtime must be investigated via collection contracts, actual data, and casts used; do not lump them together as “wildcard errors.”

## 14. How to Read Compiler Capture Error Messages

When trying to pass an `Integer` into `List<? extends Number>`:

```java
static void addBad(List<? extends Number> values) {
    // values.add(10); // Does not compile.
}
```

A compiler message might mention `CAP#1`, that `Integer` cannot be converted to `CAP#1`, or “where CAP#1 is a fresh type-variable”. This is how the compiler expresses:

- `CAP#1` is the unknown element type of `values`;
- `CAP#1` is known to have upper bound `Number`;
- yet there is no proof that `Integer <: CAP#1`;
- therefore the call `add(10)` is unsafe.

Do not depend on exact `CAP#1` numbering or message wording, as compiler versions can format diagnostics differently.

When encountering this kind of type error, ask yourself in sequence:

1. Does the generic at the parameter position declare a bound `T extends ...`?
2. Is the wildcard at the use site `?`, `? extends B`, or `? super B`?
3. From those two facts, what are the capture's upper/lower bounds?
4. Is the code **reading** from the capture or **writing** a value into the capture?
5. If both reading and writing the same unknown type are needed, should the operation move into a generic helper `<E>` so the compiler preserves the type link?

The right fix is usually changing the signature to a producer `? extends T`, a consumer `? super T`, or a generic helper, rather than using an unchecked cast.

## 15. Practice Questions

**Question 1.** With `List<? extends Number> values`, what does the compiler guarantee?

- Capture upper bound: `Number`.
- Capture lower bound: the `null` type.
- `Number n = values.get(0)` is type-valid, though `get(0)` can still encounter an empty list.
- `values.add(10)` is invalid; `values.add(null)` is type-valid but not guaranteed to succeed at runtime.

**Question 2.** With `List<? super Integer> values`, what are the upper and lower bounds?

- Upper bound: `Object`, since `List<E>` has no tighter bound.
- Lower bound: `Integer`.
- `values.add(10)` is valid; `Object v = values.get(0)` is valid.
- `Number n = values.get(0)` is not guaranteed.

**Question 3.** With `NumberBox<T extends Number>` and `NumberBox<? super Integer>`, what variable type can receive the result of `get`?

**`Number`.** The upper bound of `CAP` is `Number`; the lower bound is `Integer`. Thus `Number n = box.get()` is accepted without a cast.

**Question 4.** Can `NumberBox<?>` read `Number`?

**Yes.** The unbounded wildcard inherits the upper bound from the class's `T extends Number` parameter; `?` does not strip `T`'s declared bound.

**Question 5.** Can you copy directly from `List<? extends Number> a` to `List<? extends Number> b` via `b.add(a.get(0))`?

**No.** The captures of the two sources are independent; `b` could be `List<Integer>` while `a` could be `List<Double>`. If the destination must accept any `Number`, declare the destination `List<? super Number>`.

**Question 6.** Why does a generic helper `<E> void helper(List<E> values)` fix certain `List<?>` errors?

Because the compiler infers `E` as **the specific captured type for one call**, then uses that single type parameter `E` throughout the helper body. That makes it possible to retrieve an element of type `E` and put it back into the same `List<E>` safely.

## 16. Key Takeaways to Apply

- Wildcard capture creates **a temporary unknown yet bounded type**; it does not create a new runtime type.
- `? extends B` gives an **upper** bound from `B` combined with the declared bound, and a `null`-type **lower** bound: convenient for **reading**.
- `? super B` gives a **lower** bound of `B`, and an **upper** bound from the generic parameter's declared bound: convenient for **writing** values of `B`.
- `?` also takes its upper bound from the declared bound and has a `null`-type lower bound; therefore `NumberBox<?>` can read `Number` while `List<?>` usually only reads `Object`.
- Two identical-looking wildcards can be **two separate captures**; identical bounds do not force actual type arguments to be identical.
- When values must move between positions genuinely using **the same unknown type**, a generic helper `<E>` names the captured type and preserves that relationship.
- Always distinguish **type validity** from whether a collection is modifiable, allows `null`, or satisfies runtime data requirements.

The decisive question when analyzing a piece of Java Generics code is: **“What upper bound does this CAP type have for reading, what lower bound does it have for writing, and do the operating sites genuinely use the same CAP?”**