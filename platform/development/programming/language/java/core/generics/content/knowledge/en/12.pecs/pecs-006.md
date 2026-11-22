# Constraining Multiple Inputs to Share a Type in Java Generics and PECS

When a Java method takes multiple lists, collections, or generic values, we often need to express **relationships between parameters**: elements from multiple sources must be handled under a common type, data transferred to a destination must be safe, and the return value must preserve type information.

A method type parameter, such as `<T>`, lets us give **a shared type name** used in multiple positions within the same signature. Combined with the **PECS** (*Producer Extends, Consumer Super*) rule, we can write:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T value : first) {
        destination.add(value);
    }
    for (T value : second) {
        destination.add(value);
    }
}
```

Here, `first` and `second` are **sources supplying** elements compatible with `T`; `destination` is a **destination receiving** values of type `T`. All three parameters are checked through **the same `T` for each call**, enabling the compiler to verify the data flow.

An important point to grasp right away: sharing `T` in `List<? extends T>` **does not force both sources to have the exact same element type**. For example, a `List<Integer>` source and a `List<Double>` source can still participate in the same call with `T = Number`. If you want to require both lists to have **the exact same type argument**, a `List<T>` signature in both positions establishes a different contract.

## 1. What Does “Multiple Inputs Sharing a Type” Mean?

Consider a method processing two lists:

```java
static <T> void inspect(List<T> left, List<T> right) {
    T firstLeft = left.get(0);
    T firstRight = right.get(0);
    System.out.println(firstLeft + " | " + firstRight);
}
```

`<T>` is declared **once** before the method's return type; occurrences of `T` in the signature and body refer to **the same type parameter**. With arguments `List<String>` and `List<String>`, the compiler can infer `T = String`. With two `List<Integer>` arguments, the compiler can infer `T = Integer`.

In this signature, `List<T>` is *invariant*, so the two list parameters are required to match **the same type argument `T`**. Example:

```java
List<Integer> integers = List.of(1, 2);
List<Integer> moreIntegers = List.of(3, 4);
List<Number> numbers = List.of(5, 6);

inspect(integers, moreIntegers); // Valid: T is Integer.
// inspect(integers, numbers);   // Does not compile with signature List<T>, List<T>.
```

The snippet above is illustrative; it must be placed inside a class containing `inspect` and requires `import java.util.List;`.

The error on the second call occurs because `List<Integer>` is not `List<Number>`. Java cannot simply choose `T = Number` to turn `List<Integer>` into `List<Number>`; generics such as `List<E>` are not covariant in their type arguments.

**The concept of “sharing one `T`” has two distinct design levels**:

1. `List<T>` in multiple positions: the list parameters must use the same type argument under generic compatibility rules.
2. `List<? extends T>` in multiple positions: each list may have its own element type, as long as all are `T` or subtypes of `T`.

Both share the name `T`, but **their promises about the input arguments differ**.

## 2. The `<T>` Type Parameter and the Role of Type Inference

In a generic method:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

the `T` positions are constrained by the same method type variable. However, do not interpret `T` as a promise that **two runtime objects must have the same class**. The call:

```java
Number value = chooseFirst(10, 2.5);
```

can be valid because the compiler finds a common type compatible with `Integer` and `Double` that also fits the result context, such as `Number`. Both parameters `T first` and `T second` receive values whose types are subtypes of `T` via method invocation conversion.

The difference appears with invariant generics:

```java
static <T> void acceptLists(List<T> first, List<T> second) {
    // Both List<T> parameters require the same type argument T.
}
```

Even though `Integer` and `Double` both extend `Number`, a `List<Integer>` cannot automatically convert to `List<Number>` to match `List<T>`. When we need to allow **sources of different types that share a common supertype**, we must express that relationship explicitly with `? extends T`.

Do not overuse `<T>` merely to stand in for a concrete type when there is no relationship to preserve. The value of a shared type parameter lies in **linking multiple positions** in the signature and letting the compiler check them consistently.

## 3. Two Producers: Combining `List<? extends T>` with `List<? extends T>`

A method wanting to read two sources whose element types may differ should declare:

```java
static <T> List<T> combine(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

Both inputs are *producers*: they supply data that we can read as type `T`. Each wildcard may represent a different subtype of `T`; it is neither the same wildcard capture nor two lists with the exact same element type.

For example, `List<Integer>` and `List<Double>` can both be read as `Number`. If the variable receiving the result has type `List<Number>`, the compiler can choose `T = Number`.

### Runnable Java 17 Example: Combining Two Sources

Save as `SharedProducerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SharedProducerDemo {
    static <T> List<T> combine(
            List<? extends T> first,
            List<? extends T> second) {
        List<T> result = new ArrayList<>();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(2.5, 3.5);

        List<Number> allNumbers = combine(integers, doubles);
        System.out.println(allNumbers);

        List<String> allWords = combine(
                List.of("Java"),
                List.of("Generics"));
        System.out.println(allWords);

        // List<Integer> wrong = combine(integers, doubles);
        // Does not compile: Double cannot be an Integer.
    }
}
```

Compile and run:

```bash
javac SharedProducerDemo.java
java SharedProducerDemo
```

Output:

```text
[1, 2, 2.5, 3.5]
[Java, Generics]
```

The `combine` method creates a new list, so calling `addAll` on `result` is supported because `ArrayList` is modifiable. Elements taken from each source are allowed to be added to `List<T>` because the compiler has proven the sources' element types are `T` or subtypes of `T`.

When the entire result needs to preserve type `Integer`, a `List<Double>` source will not fit. No safe cast turns a `Double` value into an `Integer` through generics alone.

## 4. Two Producers and One Consumer: Linked by a Shared `T`

The PECS rule applies most clearly when data flows **from multiple sources into one destination**:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T item : first) {
        destination.add(item);
    }
    for (T item : second) {
        destination.add(item);
    }
}
```

Meaning of each position:

| Position | Signature | Type contract |
| --- | --- | --- |
| First source | `List<? extends T>` | Read elements as type `T` |
| Second source | `List<? extends T>` | Read elements as the same shared type `T` |
| Destination | `List<? super T>` | Can add objects of type `T` |
| Method declaration | `<T>` | Links all type conditions in one call |

The compiler must find an assignment for `T` such that the sources match `? extends T` and the destination matches `? super T`. If no type satisfies everything, the call is rejected before running.

### Java 17 Example: Transferring Multiple Sources into One Destination

Save as `MultiSourcePecsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MultiSourcePecsDemo {
    static <T> void transferBoth(
            List<? extends T> first,
            List<? extends T> second,
            List<? super T> destination) {
        for (T item : first) {
            destination.add(item);
        }
        for (T item : second) {
            destination.add(item);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(2.5, 3.5);
        List<Number> numbers = new ArrayList<>();

        transferBoth(integers, doubles, numbers);
        System.out.println(numbers);

        List<Object> objects = new ArrayList<>();
        transferBoth(List.of("A", "B"), List.of(10, 20), objects);
        System.out.println(objects);

        List<Integer> integerDestination = new ArrayList<>();
        transferBoth(integers, List.of(3, 4), integerDestination);
        System.out.println(integerDestination);

        // transferBoth(integers, doubles, integerDestination);
        // Does not compile: List<Integer> destination cannot accept Double.
    }
}
```

```bash
javac MultiSourcePecsDemo.java
java MultiSourcePecsDemo
```

Output:

```text
[1, 2, 2.5, 3.5]
[A, B, 10, 20]
[1, 2, 3, 4]
```

Analysis:

1. With `List<Integer>`, `List<Double>`, and `List<Number>`, `T = Number` can be chosen: both sources can be read as `Number` and the destination can accept `Number`.
2. With `List<String>`, `List<Integer>` sources and a `List<Object>` destination, a common type such as `Object` can be chosen, sufficient to pass both element kinds.
3. With two integer sources and a `List<Integer>` destination, `T = Integer` can be chosen.
4. With a source containing `Double` and a `List<Integer>` destination, no safe `T` satisfies both the source's requirement to emit `Double` and the destination's restriction to accept `Integer`.

The example illustrates **type constraints across multiple parameters**. It does not make Java convert `Double` objects into `Integer` or `String` into new `Object` instances; the operations simply transfer the same object references through the list interface.

## 5. “Sharing a `T`” Does Not Mean the Sources Have the Exact Same Type

This is the easiest point to confuse.

Compare two signatures:

```java
static <T> void exactArguments(List<T> left, List<T> right) {
    // Both Lists use the same type argument T.
}

static <T> void commonSupertype(
        List<? extends T> left,
        List<? extends T> right) {
    // Each List can use a different subtype of T.
}
```

Given:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

// exactArguments(ints, doubles); // Does not compile.
commonSupertype(ints, doubles);   // Can infer a shared T.
```

Note: the snippets in this section only illustrate syntax and compilation conditions; to run standalone, place them in a class, add `import java.util.List;`, and a `main` method.

**Why is `List<T>` stricter?** The type parameter `T` sits inside invariant `List<T>`. When one argument is `List<Integer>`, it imposes a type-argument equality constraint matching `Integer`; the `List<Double>` argument imposes a conflicting constraint.

**Why is `List<? extends T>` more flexible?** The source parameter only needs a type argument that is `T` or a subtype of `T`. `Integer` and `Double` share the supertype `Number`, so the condition can be satisfied simultaneously.

Also, do not equate `<T> void accept(T a, T b)` with `<T> void accept(List<T> a, List<T> b)`. In the first, each `Integer` or `Double` value can convert to a common supertype when passed as an argument; in the second, two invariant containers cannot convert their type arguments in that manner.

## 6. Upper Bounds on `T` Restrict the Shared Type Domain

If the goal is only to process numbers, we can add a bound:

```java
static <T extends Number> double sumBoth(
        List<? extends T> first,
        List<? extends T> second) {
    double sum = 0;
    for (Number value : first) {
        sum += value.doubleValue();
    }
    for (Number value : second) {
        sum += value.doubleValue();
    }
    return sum;
}
```

The compiler needs to find a `T` that is `Number` or a subtype of `Number`, and also a common supertype suitable for both sources. Two sources `Integer` and `Double` can share `T = Number`. However, if one source is `List<String>`, there is no valid inference satisfying `T extends Number`.

Save as `BoundedInputsDemo.java`:

```java
import java.util.List;

public class BoundedInputsDemo {
    static <T extends Number> double sumBoth(
            List<? extends T> first,
            List<? extends T> second) {
        double result = 0;
        for (Number number : first) {
            result += number.doubleValue();
        }
        for (Number number : second) {
            result += number.doubleValue();
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(sumBoth(
                List.of(1, 2),
                List.of(0.5, 1.5)));

        // sumBoth(List.of(1), List.of("hello"));
        // Does not compile: String is not a Number.
    }
}
```

```bash
javac BoundedInputsDemo.java
java BoundedInputsDemo
```

Output:

```text
5.0
```

The bound `T extends Number` lets code inside the method body use `Number`'s API. However, a type bound does not prevent `null` values from appearing in sources that permit `null`. The `sumBoth` snippet assumes supplied elements are non-`null` numbers; otherwise, `number.doubleValue()` can cause `NullPointerException`. Real APIs should state or validate data assumptions.

## 7. The Return Type Can Also Share `T` with Multiple Inputs

Type constraints apply not only to input parameters. A return type of `T` or `List<T>` helps preserve the relationship across the call boundary:

```java
static <T> List<T> combine(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

Because of the return type `List<T>`, the assignment context can also participate in inference:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

List<Number> combined = combine(ints, doubles); // Valid.

// List<Integer> wrong = combine(ints, doubles);
// Does not compile: Integer output requirement cannot accommodate Double.
```

If the signature were changed to `List<?> combine(List<?> a, List<?> b)`, the method could still hold and return elements, yet the caller could only read the result as `Object` and would lose the shared type information that `<T>` can maintain.

This is a key design criterion: **when there is a type relationship across multiple parameters and the result, use a shared name `T` to describe that relationship**. Independent `?` wildcards are typically appropriate when the caller and method do not need to preserve that connection.

## 8. Multiple `?` Wildcards Do Not Automatically Link Together

Consider the method:

```java
static void inspectUnknown(List<?> first, List<?> second) {
    Object a = first.get(0);
    Object b = second.get(0);
    System.out.println(a + ", " + b);
}
```

Each `?` denotes a **separate** unknown type argument. You cannot deduce that `first`'s elements have the same type as `second`'s elements.

Similarly, the signature:

```java
static void acceptTwo(
        List<? extends Number> first,
        List<? extends Number> second) {
    // Both sources can be read as Number.
}
```

guarantees both lists contain numbers when read through static typing, but does not assert that both lists have the exact same element type. `List<Integer>` and `List<Double>` are both valid.

With a generic method:

```java
static <T> void acceptLinked(
        List<? extends T> first,
        List<? extends T> second) {
    // There is a shared T; each wildcard can capture a different subtype.
}
```

you still cannot execute `first.add(second.get(0))`, because `first` has an unknown captured element type and might be `List<Integer>` while `second` is `List<Double>`. **A shared type `T` only guarantees elements can be read as `T`**; it is not enough to allow writing an element from one source directly into the other source.

If you need to transfer elements, pass them into a **suitable consumer**, or take exact `List<T>` lists when you genuinely require the same element type and appropriate write operations.

## 9. Why Not Use `List<Object>` or Casts to Simplify?

A less flexible way to write this is:

```java
static void transferOnlyObjects(
        List<Object> source1,
        List<Object> source2,
        List<Object> destination) {
    destination.addAll(source1);
    destination.addAll(source2);
}
```

This does not directly accept `List<String>` or `List<Integer>` because `List<String>` is not `List<Object>`. Callers may be forced to create new lists or use unsafe casts.

If the signature genuinely only needs to **read sources and write into a common-supertype destination**, `<T>` + PECS expresses the intent more accurately:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T value : first) destination.add(value);
    for (T value : second) destination.add(value);
}
```

The compiler verifies types automatically. Avoid raw types or `(List)` to force a `List<Integer>` into `List<Number>`: those approaches can break type safety and cause `ClassCastException` at later read sites.

Still, **not every method needs to be generic**. If business logic truly requires every input to already be `List<Object>` and rejects other parameterized list kinds, declaring concrete types can be appropriate. The decision comes from **the desired data contract**, not a desire to use as much generic syntax as possible.

## 10. Connection to the `Collections.copy` API

The Java standard library has a method with a familiar PECS idea:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

This is the conceptual signature of `java.util.Collections.copy`. `src` is the producer, `dest` is the consumer, both sharing `T`; hence you can copy from `List<Integer>` into `List<Number>`.

Note: `Collections.copy` **overwrites existing elements** in the destination and requires the destination list to be long enough; it is **not** an `addAll` method that automatically grows the destination's size.

In the **two-source** problem, we generalize this model by tying both sources to one `T`:

```java
static <T> void appendAll(
        List<? extends T> sourceA,
        List<? extends T> sourceB,
        List<? super T> destination) {
    destination.addAll(sourceA);
    destination.addAll(sourceB);
}
```

`appendAll` requires the destination to support adding elements; the compiler only checks the type relationship, not whether the destination collection is modifiable. For example, `List.of(...)` can satisfy the parameter type-wise yet still throw `UnsupportedOperationException` when `addAll` attempts mutation.

If data from the two sources has no common type meeting the destination's capability, the compiler rejects the call rather than letting a type error surface after writing.

## 11. When an API Needs to Constrain Exact Same Element Type

Suppose two lists are two versions of **the exact same kind of data**, and the method needs to swap elements between them. Then we can write:

```java
static <T> void exchangeFirst(List<T> first, List<T> second) {
    T temporary = first.get(0);
    first.set(0, second.get(0));
    second.set(0, temporary);
}
```

Here `List<T>` in both positions **intentionally requires the same type argument**. A `List<Integer>` and a `List<Number>` are not automatically treated as a same-element-type pair for calling this method directly.

Complete Java 17 example, saved as `SameTypeSwapDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SameTypeSwapDemo {
    static <T> void exchangeFirst(List<T> first, List<T> second) {
        T previous = first.get(0);
        first.set(0, second.get(0));
        second.set(0, previous);
    }

    public static void main(String[] args) {
        List<String> first = new ArrayList<>(List.of("left", "keep"));
        List<String> second = new ArrayList<>(List.of("right", "stay"));

        exchangeFirst(first, second);
        System.out.println(first);
        System.out.println(second);

        List<Integer> ints = new ArrayList<>(List.of(1));
        List<Number> numbers = new ArrayList<>(List.of(2));
        // exchangeFirst(ints, numbers); // Does not compile.
    }
}
```

```bash
javac SameTypeSwapDemo.java
java SameTypeSwapDemo
```

Output:

```text
[right, keep]
[left, stay]
```

`exchangeFirst` requires both lists to be non-empty and allow `set`. These assumptions are met by the `ArrayList` example, but are not guaranteed by generics themselves. Unmodifiable or empty lists can throw exceptions at runtime. That is a collection API limitation, separate from type-relationship checking.

Do not add `? extends T` to every parameter just because of PECS: when a function must **read and write back** the exact element type in both lists, `List<T>` usually expresses the constraint better.

## 12. Common Mistakes and Fixes

### Mistake 1: Using `List<T>` When Wanting to Accept Two Producers with Different Subtypes

```java
static <T> void consumeBoth(List<T> a, List<T> b) {
    // ...
}
```

Calls with `List<Integer>` and `List<Double>` will not match because generic lists are invariant.

**Fix:** when the method only reads from both lists, consider `List<? extends T>` for both, with a shared `<T>`.

### Mistake 2: Using Two `?` Wildcards and Assuming They Are the Same Type

```java
static void wrongAssumption(List<?> a, List<?> b) {
    Object value = b.get(0);
    // a.add(value); // Does not compile.
}
```

There is no relationship forcing the element types of `a` and `b` to match. Switch to `List<T>` if the same type argument is required for transferring elements, or transfer elements through a separate consumer `List<? super T>` if only a common supertype is needed.

### Mistake 3: Confusing `? extends T` with a Promise That Both Sources Have the Exact Same Type

```java
static <T> void accept(List<? extends T> left,
                       List<? extends T> right) {
    // A shared T does not mean the two wildcard captures are the same.
}
```

`List<Integer>` and `List<Double>` can be passed, so you cannot automatically write an element from one source into the other.

### Mistake 4: Choosing Too Narrow a Destination for the Sources

```java
List<Integer> ints = List.of(1);
List<Double> doubles = List.of(2.5);
List<Integer> destination = new ArrayList<>();

// transferBoth(ints, doubles, destination); // Does not compile.
```

**Fix:** if the destination must hold both numeric kinds, use `List<Number>` or a suitable common supertype as the destination's element type.

### Mistake 5: Using `List<Object>` Instead of Appropriate Wildcards

`List<Object>` does not directly accept `List<String>` or `List<Integer>`. If the method only observes data, use `List<?>`; if you need to maintain relationships across multiple sources/destinations, use a type parameter `<T>` with wildcard bounds.

### Mistake 6: Thinking `T` Is Inferred from Just One Argument

The compiler considers **all constraints of the call**, including sources, destination, `T extends ...` bounds, and sometimes the expected result type. If one argument forces a `T` incompatible with another argument, the call is rejected. Do not pick `T` separately for each position and assume they match.

### Mistake 7: Confusing Type Safety with Collection Mutability

`List<? super T>` allows the compiler to accept adding `T`, yet the actual collection might not support `add` or may have rules about `null`. PECS type guarantees and collection runtime contracts are separate concerns.

## 13. Self-Check Questions

**Question 1.** Given two lists `List<Integer>` and `List<Double>`, can the following method be called?

```java
static <T> void read(List<? extends T> a,
                     List<? extends T> b) { }
```

**Yes.** The compiler can choose an appropriate common supertype such as `Number`. The two wildcard captures do not need to be equal.

**Question 2.** Can those two lists call `static <T> void read(List<T> a, List<T> b)`?

**No**, because `List<Integer>` and `List<Double>` are distinct invariant parameterizations.

**Question 3.** If the two sources are `List<Integer>` and `List<Double>`, does a `List<Number>` destination fit the signature `<T> void transferBoth(List<? extends T>, List<? extends T>, List<? super T>)`?

**Yes.** `T = Number` can be chosen and all numeric elements added to the destination.

**Question 4.** What if the destination is changed to `List<Integer>`?

**Invalid** because the `List<Double>` source contains an element type that cannot be safely written into `List<Integer>`.

**Question 5.** Should a method that needs to swap elements back and forth between two lists use two `List<? extends T>` parameters?

**Not necessarily; usually it should use two `List<T>` parameters** because it needs to read and write elements of the exact same type. `? extends T` is primarily suited when the parameter is a producer.

**Question 6.** Why does `<T>` appear once in a signature yet get used in multiple places?

Because a type parameter must be declared once and has scope throughout the method's signature and body. Using the same `T` in multiple places enables the compiler to verify a consistent relationship among sources, destination, and result.

## 14. Signature Selection Guide

Start from **the desired data direction and type relationships**:

1. If multiple parameters must be lists with **the exact same type argument** and may read/write back and forth, use `<T> ... (List<T> a, List<T> b)`.
2. If multiple sources may hold **different subtypes of a common type**, use `<T> ... (List<? extends T> a, List<? extends T> b)`.
3. If data from those sources needs to be **added into a destination**, use `List<? super T>` for the destination to connect the PECS relationship.
4. If the data domain must belong to a specific family, add a bound to `T`, such as `<T extends Number>`.
5. If the result type must accurately reflect its relationship to the sources, use `T` or `List<T>` in the return type.
6. If no relationship is needed between elements or between parameters, `List<?>` may suffice and be easier to read than an unnecessary generic method.

**Key takeaway:** `<T>` names **a shared type variable**; `? extends T` allows each source to be a producer of `T` or a subtype; `? super T` allows the destination to receive `T`. Good design clearly distinguishes “sharing `T` to connect data flow” from “lists having the exact same type argument.”
