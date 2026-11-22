# Type Relationships Between Bounded Wildcards

## 1. Objective and Context

In Java Generics, an inheritance relationship between two element types **does not automatically create an inheritance relationship between two generic types**. For example, because `Integer` is a subtype of `Number`, we can assign an `Integer` to a `Number` variable, yet we cannot assign a `List<Integer>` to a `List<Number>` variable.

Bounded wildcards help accurately describe the group of element types accepted by a generic parameter. This lesson focuses on **type relationships between wildcard usages**: when a `List<? extends A>` can be assigned to a `List<? extends B>`, when a `List<? super A>` can be assigned to a `List<? super B>`, and why the two directions are opposite.

After this lesson, you should be able to determine valid assignment directions yourself, distinguish read/write capabilities, write APIs using PECS, and explain wildcard-related compile errors.

## 2. Three Foundational Concepts

Suppose `Integer` is a subtype of `Number` and `Number` is a subtype of `Object`:

```text
Integer <: Number <: Object
```

The notation `S <: T` means a value of type `S` can be used where `T` is required under subtyping. For `List`, distinguish:

- `List<Integer>`: elements have the exact type `Integer` per the generic declaration.
- `List<? extends Number>`: a list with an **unknown** element type, where that type is `Number` or a subtype of `Number`.
- `List<? super Integer>`: a list with an **unknown** element type, where that type is `Integer` or a supertype of `Integer`.

Wildcards do not change the runtime type of an object. They change what **the compiler can guarantee** when we use a generic reference.

### 2.1. Invariance

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // COMPILE ERROR
```

If the assignment line above were allowed, subsequent code could call `numbers.add(3.14)` and break the promise that `integers` holds only `Integer`. Therefore, `List<Integer>` and `List<Number>` have no subtype relationship merely because `Integer <: Number`.

### 2.2. A Wildcard Represents an Unknown Element Type

`List<? extends Number>` is not synonymous with `List<Number>`: the actual list may be `List<Integer>`, `List<Double>`, or `List<Number>`. Similarly, `List<? super Integer>` may reference `List<Integer>`, `List<Number>`, or `List<Object>`.

The `?` mark means **there is a specific actual type, yet we do not know exactly which one it is**. Therefore, you cannot arbitrarily treat it as `Number`, `Integer`, or `Object` at will.

## 3. Subtyping Rule for `? extends`

Given `A <: B`, the following relationship is valid when both sides use the same generic type `G`:

```text
G<? extends A> <: G<? extends B>
```

This is the **upper-bound widening direction**: a list with a narrower upper bound (`Integer`) can be used as a list with a broader upper bound (`Number`). Reason: every type that does not exceed `Integer` also does not exceed `Number`.

```java
List<? extends Integer> source = List.of(10, 20);
List<? extends Number> target = source; // VALID
Number value = target.get(0);           // VALID
```

The reverse direction is unsafe:

```java
List<? extends Number> source = List.of(1.5, 2.5);
// List<? extends Integer> target = source; // COMPILE ERROR
```

`source` could actually be a `List<Double>`. Java cannot guarantee that all elements are `Integer`.

Key point: **what is changing is the wildcard bound**, not Java allowing `List<Integer>` to become `List<Number>`.

### 3.1. Valid Assignments from a Concrete Type

```java
List<Integer> ints = List.of(1, 2);
List<? extends Integer> a = ints;
List<? extends Number> b = ints;
List<? extends Object> c = ints;
List<?> d = ints;
```

All of these are valid. Each variable `a`–`d` holds the same reference to the original list, yet the wider the upper bound becomes, the less the compiler knows about the element type when reading.

### 3.2. Consequences for Reading and Writing

With `List<? extends Number>`:

- Elements can be read as `Number`, because every accepted type is a subtype of `Number`.
- You cannot add an `Integer`, `Double`, or arbitrary `Number`, because the actual element type could be another subtype.
- `add(null)` is type-valid (if the list structure supports adding), because `null` is compatible with every reference type.

```java
List<? extends Number> numbers = new ArrayList<Integer>();
Number n = numbers.get(0); // Illustrative code for type checking only; list is empty so this line is not executed.
// numbers.add(123);       // COMPILE ERROR
numbers.add(null);         // Type-valid; ArrayList in the example is mutable.
```

Remember that **being allowed to compile** does not mean a given implementation always permits modification: `List.of(...)` is immutable and can throw `UnsupportedOperationException` even for a type-valid mutating operation.

## 4. Subtyping Rule for `? super`

Again suppose `A <: B`. For lower bounds, the relationship reverses direction:

```text
G<? super B> <: G<? super A>
```

Example:

```java
List<? super Number> source = new ArrayList<Object>();
List<? super Integer> target = source; // VALID
target.add(7);                        // VALID
```

Explanation: every type capable of holding `Number` (such as `Number` or `Object`) can certainly also hold `Integer`. However, a list guaranteed only to hold `Integer` is not necessarily able to hold every `Number` (for instance, `Double`).

The reverse direction is invalid:

```java
List<? super Integer> source = new ArrayList<Integer>();
// List<? super Number> target = source; // COMPILE ERROR
```

If that assignment were allowed, `target.add(3.14)` would insert a `Double` into a `List<Integer>`.

### 4.1. Valid Assignments from Concrete Types

```java
List<Integer> ints = new ArrayList<>();
List<Number> nums = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = ints;
List<? super Integer> b = nums;
List<? super Integer> c = objects;

List<? super Number> d = nums;
List<? super Number> e = objects;
// List<? super Number> f = ints; // COMPILE ERROR
```

### 4.2. Consequences for Reading and Writing

With `List<? super Integer>`:

- You can add `Integer` and subtypes of `Integer` (in practice `Integer` is `final`).
- You cannot add an arbitrary `Number`, because the actual list may be just `List<Integer>`.
- Values read back are only guaranteed to have type `Object`: the actual element type could be `Integer`, `Number`, or `Object`.

```java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(42);
Object item = sink.get(0);
// Integer value = sink.get(0); // COMPILE ERROR: only Object is guaranteed.
// sink.add(3.14);              // COMPILE ERROR: Double is not an Integer.
```

Casting `(Integer) item` is only valid at runtime if the object actually is an `Integer`; wildcards do not permit inferring that for every element.

## 5. Relationship Diagram and How to Remember It

With `Integer <: Number <: Object`, the following arrows show valid left-to-right assignments:

```text
Upper-bound branch (? extends):
List<Integer>
    -> List<? extends Integer>
    -> List<? extends Number>
    -> List<? extends Object> (equivalent in bound to List<?>)

Lower-bound branch (? super):
List<Object>
    -> List<? super Number>
    -> List<? super Integer>
    -> List<?>

In addition:
List<Number> -> List<? extends Number>
List<Number> -> List<? super Number>
List<Number> -> List<? super Integer>
List<Integer> -> List<? super Integer>
```

| Case | Relationship direction when `A <: B` | What is guaranteed |
| --- | --- | --- |
| Upper bound `extends` | `G<? extends A> <: G<? extends B>` | Readable at least as `B` |
| Lower bound `super` | `G<? super B> <: G<? super A>` | Values of type `A` can be written |
| Concrete generic | `G<A>` does **not** imply `G<B>` | Invariant with respect to type arguments |
| Unbounded `?` | `G<T>`, `G<? extends T>`, and `G<? super T>` can all be assigned to `G<?>` | Safe to read as `Object` |

When reading the diagram, do not infer that `List<? extends Number>` and `List<? super Integer>` have a direct subtype relationship with each other. Both can reference the same `List<Number>`, yet a variable of the first type cannot automatically be assigned to a variable of the second type: each variable carries different guarantees.

## 6. Complete, Runnable Java 17+ Example

Save as `WildcardRelationsDemo.java`. The program illustrates **both valid assignment directions** and transferring data from producer to consumer.

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardRelationsDemo {
    static <T> void copyAll(List<? extends T> source, List<? super T> target) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);

        // Upper bound: Integer -> Number.
        List<? extends Integer> integerProducer = integers;
        List<? extends Number> numberProducer = integerProducer;
        Number first = numberProducer.get(0);

        // Lower bound: super Number -> super Integer.
        List<Object> objects = new ArrayList<>();
        List<? super Number> numberConsumer = objects;
        List<? super Integer> integerConsumer = numberConsumer;
        integerConsumer.add(3);

        Object inserted = integerConsumer.get(0);

        List<Number> numbers = new ArrayList<>();
        copyAll(integers, numbers);

        System.out.println(first);
        System.out.println(objects);
        System.out.println(inserted);
        System.out.println(numbers);
    }
}
```

Compile and run:

```bash
javac WildcardRelationsDemo.java
java WildcardRelationsDemo
```

Exact stdout output:

```text
1
[3]
3
[1, 2]
```

In `copyAll`, `source` produces values of type `T` (`? extends T`), while `target` receives values of type `T` (`? super T`). With `T = Integer`, `List<Integer>` is a valid source and `List<Number>` is a valid destination. The example builds its own `copyAll` method in the sense of **appending** to the target; unlike `Collections.copy(dest, src)`, which requires the destination list to already have enough element slots to overwrite.

## 7. PECS and API Design

**PECS = Producer Extends, Consumer Super**: choose wildcards based on **how the method uses the data**.

If a parameter only supplies elements for you to read, use `? extends T`:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number number : values) {
        total += number.doubleValue();
    }
    return total;
}
```

`sum` works with `List<Integer>`, `List<Double>`, and `List<Number>` without casting or copying lists.

If a parameter only receives elements you insert into it, use `? super T`:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

`addDefaults` works with `List<Integer>`, `List<Number>`, and `List<Object>`.

If a method needs to both **read as T** and **write T** with the exact same element type, in many cases you should use a `<T>` type parameter instead of ambiguous wildcards:

```java
static <T> void duplicateFirst(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.add(first);
    }
}
```

This is an illustrative method declaration snippet, not a standalone program. The `List<T>` parameter maintains the correlation between the data type read out and the data type allowed to be written in.

## 8. Relationship Between Two Opposite-Direction Wildcards

There is no general rule allowing free conversion from `extends` to `super`:

```java
List<? extends Number> producer = List.of(1, 2);
// List<? super Integer> consumer = producer; // COMPILE ERROR
```

A valid `producer` might be `List<Double>`; that list is not a place where `Integer` can be inserted. Similarly:

```java
List<? super Integer> consumer = new ArrayList<Object>();
// List<? extends Number> producer = consumer; // COMPILE ERROR
```

The list in `consumer` might be `List<Object>`, containing elements that are not `Number`. To switch roles safely, design a method taking separate source and destination parameters, or keep a concretely typed reference at the point of creation rather than using unchecked casts.

A subtle point: the fact that **two wildcard types can accept the same object** does not prove they are subtypes of each other. Subtyping requires an assignment to be safe for *every* object matching the source type, not just the specific instance currently observed.

## 9. Relationships When Generics and Wildcards Are Nested

A wildcard at an inner level does not automatically make the outer generic covariant.

```java
List<List<Integer>> nested = new ArrayList<>();

// List<List<? extends Number>> invalid = nested; // COMPILE ERROR

List<? extends List<? extends Number>> valid = nested; // VALID
```

The first line fails because the direct type arguments of the outer `List` are `List<Integer>` and `List<? extends Number>`, two different types; the outer `List` remains invariant. The last line is valid because `? extends` at the outer layer allows element types that are subtypes of `List<? extends Number>`, including `List<Integer>`.

Practical rule: evaluate the relationship **at each generic level**. Do not simply see `extends Number` inside and assume any enclosing `List` layer is assignable.

### 9.1. Relationships Between Different Generic Interfaces

The two sides do not have to both be `List` if there is a genuine interface/class inheritance relationship. For example:

```java
List<Integer> ints = List.of(1, 2);
Collection<? extends Number> numbers = ints; // VALID
Iterable<? extends Number> items = numbers;  // VALID
```

Here we combine two mechanisms: `List<E>` extends `Collection<E>`, `Collection<E>` extends `Iterable<E>`, and the wildcard bound `Integer <: Number`. Do not apply this to two generics without a matching inheritance relationship.

## 10. Wildcard Capture and Inference Limits

When using a `List<?>` variable, the compiler can temporarily assign an internal name (capture) for the unknown element type. We cannot use two separate read and write operations assuming that type is `Object`:

```java
static void replaceFirstWithItself(List<?> list) {
    if (!list.isEmpty()) {
        // list.set(0, list.get(0)); // Typically COMPILE ERROR due to mismatched capture.
    }
}
```

A helper method with `<T>` can keep the captured type consistent:

```java
static void swapFirstTwo(List<?> list) {
    swapCaptured(list);
}

private static <T> void swapCaptured(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

The two methods above are an illustrative snippet to place inside a class with `import java.util.List;`. The helper does not need to know the concrete `T`; it only needs to prove that a value taken from the same list is always written back under the same `T`. For an immutable list, `set` can still throw `UnsupportedOperationException` at runtime.

Wildcard capture does not make a `List<? extends Number>` variable able to add arbitrary `Integer` values, nor does it turn `List<? super Integer>` into a source from which `Integer` can be reliably read. It only preserves type linkage when the algorithm is genuinely safe.

## 11. Common Mistakes and How to Fix Them

| Wrong assumption or operation | Why it is wrong | How to fix |
| --- | --- | --- |
| Directly assigning `List<Integer>` to `List<Number>` | Generics are invariant | Accept `List<? extends Number>` to read, or copy elements into a new `List<Number>` |
| Calling `add(1)` on `List<? extends Number>` | The element type might be `Double` | Use `List<? super Integer>` if needing to add `Integer` |
| Reading `Integer` directly from `List<? super Integer>` | The list might hold `Number` or other `Object` elements | Read as `Object`; only check/cast when justified at runtime |
| Thinking `? super Integer` is a subtype of `? super Number` | The lower-bound direction is reversed | Remember `? super Number` can be assigned to `? super Integer` |
| Assigning `List<? extends Number>` to `List<? extends Integer>` | The upper bound is narrowed; it might hold `Double` | Keep the `Number` bound or prove the actual type through API design |
| Using raw `List` to avoid errors | Loses type checking, risks `ClassCastException` | Use wildcards or type parameters |
| Unchecked cast `(List<Number>)(List<?>) ints` | Hides the invariance error, can break type contracts | Use a generic method, appropriate wildcard, or create a new list |
| Assuming wildcards determine mutability | Type checking and runtime mutability support are independent | Distinguish compile errors from `UnsupportedOperationException` |

You cannot write a wildcard with two bounds simultaneously such as `? extends Number super Integer`. If you need to express complex constraints, consider type parameters and redesigning the API. Intersection bound syntax like `<T extends Number & Comparable<T>>` belongs to type parameter declarations, and does not mean you can write `? extends Number & Comparable<?>` as an ordinary wildcard.

Furthermore, generics in Java are primarily checked at compile time and have their type argument information erased at runtime (type erasure). You cannot use `instanceof List<? extends Number>` to check a list's element subtype at runtime; `instanceof List<?>` checks the general raw type without validating element types.

## 12. Self-Check Exercise

Suppose you already have:

```java
List<Integer> ints = new ArrayList<>();
List<Number> nums = new ArrayList<>();
List<Object> objs = new ArrayList<>();
```

Predict independently for each line whether it compiles:

```java
List<? extends Number> q1 = ints;                    // (1)
List<? super Integer> q2 = nums;                      // (2)
List<? super Number> q3 = ints;                       // (3)
List<? extends Integer> q4 = nums;                    // (4)
List<? super Number> q5 = objs;                       // (5)
List<? super Integer> q6 = q5;                        // (6)
List<? extends Number> q7 = q1;                       // (7)
List<? super Integer> q8 = q1;                        // (8)
```

**Answers:** (1) valid because `Integer <: Number`; (2) valid because `Number` can hold `Integer`; (3) invalid because `List<Integer>` cannot hold every `Number`; (4) invalid because `List<Number>` does not guarantee only `Integer`; (5) valid because `Object` is a supertype of `Number`; (6) valid along the lower-bound direction (`? super Number` to `? super Integer`); (7) valid because it is the same wildcard type; (8) invalid because the producer is not guaranteed to accept `Integer`.

**Follow-up check:** Can a `List<? extends Number>` be read as `Object`? **Yes**: `Number` is a subtype of `Object`. Can `add(null)` be called on a `List<? super Integer>`? **Yes at the type level** (if the list allows modification). Neither of these reverses the main rules.

## 13. Checklist When Reading Generic Compiler Errors

1. Identify the base element types `A`, `B` and their actual subtype relationship (if any).
2. Check whether the object is being **read**, **written**, or both.
3. For `extends`, remember a wider upper bound allows accepting a source with a narrower bound.
4. For `super`, remember a narrower lower bound allows accepting a source with a wider bound.
5. Check every level of nested generics; do not overlook invariance at the outer layer.
6. If the assignment is still invalid, ask whether a `<T>` parameter linking source and target is needed instead of a raw cast.
7. After compilation succeeds, separately check whether the list can be mutated at runtime.

## 14. Further Reading

- Oracle Java Tutorials — [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html): diagram of `extends` and `super` relationships.
- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): producer/consumer principles.
- Java Language Specification (Java SE 17), [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard syntax and containment rules.

**Key point:** Given `A <: B`, we have `G<? extends A> <: G<? extends B>`, yet `G<? super B> <: G<? super A>`. These two rules allow describing flexible read/write APIs while preserving Java's type checking.