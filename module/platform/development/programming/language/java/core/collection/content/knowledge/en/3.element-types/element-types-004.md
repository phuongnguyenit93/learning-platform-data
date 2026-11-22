# Upper-Bounded Wildcards When Reading Data

## 1. The Problem: One Algorithm Reading Multiple Related Element Types

We want to compute the sum of a group of numbers. The input data could be a `List<Integer>`, a `List<Double>`, or a collection containing `Number` objects.

A `Collection<Number>` parameter cannot accommodate all of those inputs:

```java
// Signature sketch, not a standalone program.
static double sum(Collection<Number> values)
```

`Integer` is a subtype of `Number`, but `Collection<Integer>` is not a subtype of `Collection<Number>`. If such an assignment were allowed, code acting through a `Collection<Number>` reference could add a `Double` to an object expected to contain only `Integer` elements.

An upper-bounded wildcard solves the case where an algorithm needs to **read data through a common type**, without needing to arbitrarily insert new elements into the source:

```java
// Signature sketch; requires import java.util.Collection.
static double sum(Collection<? extends Number> values)
```

How to read it:

> Accepts a collection whose specific element type is `Number` or some subtype of `Number`.

From there, every element read out can be used as a `Number`. We do not need to know the exact subtype to call `doubleValue()`.

This article uses Java 17. It assumes basic knowledge of generics, type parameter invariance, and supertype–subtype relationships. The goal is to understand why reading works, why certain write calls fail to compile, and what limitations still exist beyond wildcards.

## 2. The Exact Meaning of ? extends T

Given:

```java
List<? extends Number> source;
```

`?` represents **an unknown type** constrained by the upper bound `Number`.

The following objects can all be assigned to that variable:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> integers = List.of(1, 2);
List<Double> decimals = List.of(0.5, 1.5);
List<Number> mixed = List.<Number>of(1, 2.5);

List<? extends Number> a = integers;
List<? extends Number> b = decimals;
List<? extends Number> c = mixed;
```

`List<? extends Number>` should not be interpreted as "a list that allows adding every kind of `Number`". That is a property of a mutable `List<Number>`, not of a reference with an unknown element type.

You can think of the unknown type as `CAP`:

```text
CAP is an unknown concrete type
CAP is Number or a subtype of Number

reading CAP -> using as Number: safe
passing an arbitrary Number where CAP is required: unproven
```

Here, `extends` includes the bound type itself, not only strict subtypes. It is also used for interface bounds; for example, `Collection<? extends CharSequence>` can accept a suitable collection of `String` or `StringBuilder`.

See [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html) and [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html).

## 3. Reading Data Safely Through an Upper Bound

### 3.1. Reading as Type Number

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<? extends Number> source = List.of(1, 2, 3);

Number first = source.get(0);
double value = first.doubleValue();

System.out.println(first); // 1
System.out.println(value); // 1.0
```

No `(Number)` cast is needed. The compiler knows the element belongs to a type no wider than `Number`.

Similarly with a loop:

```java
// Illustrative snippet with an already initialized source.
for (Number number : source) {
    System.out.println(number.doubleValue());
}
```

You can use methods declared on the upper bound, such as the numeric conversion methods of `Number`. See the [Number API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html).

### 3.2. Cannot Automatically Read as an Arbitrary Subtype

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<? extends Number> source = List.of(1.5, 2.5);

// Integer first = source.get(0); // Does not compile.
Number first = source.get(0);     // Valid.
```

The `Number` bound does not promise that an element is an `Integer`. Manually casting to `Integer` can shift errors to runtime.

If the algorithm genuinely requires properties specific to `Integer`, design the parameter or validate the data for that requirement. Do not use a wide wildcard and then implicitly assume the data is always a specific subtype.

### 3.3. var Does Not Recover the Hidden Subtype Either

If you write `var first = source.get(0);` where `source` is declared as `List<? extends Number>`, there is no basis to treat `first` as an `Integer`. The type that can be safely used is still based on the `Number` bound.

Type inference is not a mechanism that tracks "every actual run uses Integer" to unlock an API not guaranteed by the contract.

## 4. Why Can't We Add Number, Integer, or Double?

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> integers = new ArrayList<>();
List<? extends Number> source = integers;

// source.add(1);   // Does not compile.
// source.add(2.5); // Does not compile.
```

`source` may point to a `List<Integer>`. Adding a `Double` is clearly unsafe.

Why is adding an `Integer` also blocked? Because the same declared type `List<? extends Number>` could also be pointing to a `List<Double>` or another `Number` subtype. At the call site, the compiler does not know the exact type that `add` requires.

The rule protects all values assignable to the declared type, not just the initialization case the author happens to see in the example.

Similarly:

```java
// Illustrative snippet with source of type List<? extends Number>.
// source.set(0, 1);              // Does not compile.
// source.addAll(List.of(1, 2));  // Does not compile.
```

Changing `add` to `set` does not solve the problem: replacing an element still requires providing the exact unknown type.

### null Is a Special Case

`null` is convertible to any unknown reference type, so the following call is type-valid:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> backing = new ArrayList<>(List.of(9));
List<? extends Number> source = backing;
source.add(null);

System.out.println(backing); // [9, null]
```

Succeeding at runtime here also depends on `ArrayList` allowing additions and allowing `null`. If the object is `List.of(...)`, modification is rejected. If an implementation forbids `null`, it may throw a value error.

Therefore, do not use the absolute statement "nothing can ever be added" to describe wildcards. Distinguish type checking from the object's runtime policy.

## 5. An Upper-Bounded Wildcard Does Not Create Immutability

A quick mnemonic is to use `extends` for a read source. However, "a source for reading" is not a mechanism that forbids all modifications.

| Operation via `List<? extends Number>` | Type Checking | Runtime Condition |
| --- | --- | --- |
| `get(index)` and read as `Number` | Allowed | Valid index |
| Iterate as `Number` | Allowed | Source and elements match the algorithm |
| `add` a new `Integer` or `Double` | Disallowed | Blocked before runtime |
| `set` with an arbitrary `Number` | Disallowed | Blocked before runtime |
| `remove(index)` or `remove(Object)` | Callable | Object must support removal |
| `clear()` | Callable | Object must support clearing |
| `add(null)` | Type-valid | Object must allow additions and allow `null` |
| Modify through another reference to the same object | Not blocked by wildcard | Depends on that reference/object contract |

Example:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> original = new ArrayList<>(List.of(1, 2, 3));
List<? extends Number> source = original;

source.remove(0);
System.out.println(original); // [2, 3]

source.clear();
System.out.println(original); // []
```

Removal calls do not need to supply a new element of the captured type. They can still mutate the source data.

Furthermore:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = original;

original.add(3);
System.out.println(source); // [1, 2, 3]
```

Assignment neither copies the list nor creates a wrapper. Both variables reference the same object.

If the elements are mutable objects, reading a reference can also allow calling state-mutating methods declared on the bound type. A wildcard does not make the elements themselves immutable.

To prevent modification through an API, design an appropriate contract and mechanism such as an unmodifiable wrapper or an unmodifiable copy. Even a wrapper can observe changes from the backing source, and a shallow copy still shares element objects.

See [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html), [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), and [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

## 6. Writing a Real Reading Algorithm

```java
// Method declaration inside a class; requires import java.util.Collection.
static double sum(Collection<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Contract of the example:

- Accepts a non-`null` source and non-`null` elements.
- Does not add, remove, or replace elements in the source.
- An empty source produces `0.0`.
- Uses `double` representation for illustration; does not guarantee exact decimal arithmetic for currency.
- Does not support concurrent modification of the source outside an appropriate synchronization policy.

Calls:

```java
// Placed inside a method, with sum declared; requires import java.util.*.
System.out.println(sum(List.of(1, 2, 3)));   // 6.0
System.out.println(sum(List.of(0.5, 1.5))); // 2.0
```

Here `Collection` is chosen because only iteration is needed, not positional access. If the method needed `get(0)`, `List` would be required to express the necessary API.

If only iteration is needed without other collection operations, `Iterable<? extends Number>` can also be a suitable parameter type. Choose the interface based on the actual operations required, then use a wildcard for the type relationships to accept.

Not every reading algorithm should use `Number`: a business domain might require a more specific type or custom-defined arithmetic.

## 7. Distinguishing from `Collection<Number>`, `Collection<?>`, and `Collection<Object>`

| Parameter | Typical Matching Inputs | Safely Readable as What Type? | Meaning |
| --- | --- | --- | --- |
| `Collection<Number>` | `Collection<Number>` | `Number` | Has the specific element type `Number` |
| `Collection<? extends Number>` | `Collection<Integer>`, `Collection<Double>`, `Collection<Number>` | `Number` | Unknown element type, but no wider than `Number` |
| `Collection<?>` | Collection of various type arguments | `Object` | No specific requirement beyond what is known about `Object` |
| `Collection<Object>` | `Collection<Object>` | `Object` | Collection whose element type is `Object`, not a universal sink for all collections |

`Collection<?>` also has an implicit upper bound of `Object`. If an algorithm only prints elements or queries `size`, that may be enough. If it needs to call `doubleValue`, the `Number` bound provides useful type information.

`Collection<Object>` does not accept a direct assignment from `Collection<Integer>`. Do not use `Object` as a way to bypass generics invariance rules.

Similarly, `Collection<? extends Number>` does not accept `Collection<String>`. It widens the set of accepted inputs in a controlled manner without discarding type checking.

Parameterization and wildcard rules are specified in [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).

## 8. Wildcard or Named Type Parameter?

### 8.1. Only Reading Through a Common Contract: A Wildcard Is Usually Enough

```java
// Signature sketch; requires import java.util.Collection.
static double sum(Collection<? extends Number> values)
```

The method does not need to state that "the result has the same element type as the input". The result is always `double`, so naming the unknown type is unnecessary.

### 8.2. Relating the Input Type to the Result: Use T

```java
// Method declaration; requires import java.util.List.
static <T extends Number> T firstTyped(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
```

With a `List<Integer>`, the caller can receive an `Integer` without casting:

```java
// Placed inside a method, with firstTyped declared; requires import java.util.List.
Integer first = firstTyped(List.of(10, 20));
```

Compare with:

```java
// Method declaration; requires import java.util.List.
static Number first(List<? extends Number> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
```

The second return contract only promises `Number`; it does not preserve the "exact element type of the input" relationship for the caller.

A named type parameter `T` is useful when linking multiple type positions: source, destination, return type, or related arguments. Do not add a type parameter merely to make a signature look more generic. [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html)

### 8.3. Avoid Wildcards in Return Types Unless Needed

An API returning `List<? extends Number>` forces the caller to deal with an unknown type. If the API creates a list of numbers whose intended contract is `List<Number>`, it should usually declare that exact type.

Conversely, some APIs have good reason to expose elements across a type family; in those cases, a wildcard can be valuable. The decision should be based on the information the caller needs, not on mechanically applying the "use extends for reading" rule to every position in a signature.

## 9. Copying a Source into a Destination with an Explicit Type

If you need to accept various subtype sources and then add another `Number` value, do not cast the source to `Collection<Number>`. Create a new collection instead:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> original = List.of(1, 2, 3);
Collection<? extends Number> source = original;

List<Number> copy = new ArrayList<>(source);
copy.add(2.5);

System.out.println(original); // [1, 2, 3]
System.out.println(copy);     // [1, 2, 3, 2.5]
```

The constructor `ArrayList(Collection<? extends E>)` reads elements from the source to populate a list of destination type `E`. In this example, `E` is `Number`. The source retains its own contract. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

You can encapsulate this relationship:

```java
// Method declaration; requires import java.util.*.
static <T> List<T> copySource(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

This copies the collection structure and element references, not a deep clone. For mutable elements, the source and the copy may still reference the same underlying objects.

If you want to write into an already provided destination collection, that is a destination parameter design problem, typically involving `? super T`. Do not mechanically replace `extends` with `super` on the source: each side plays a different role.

## 10. Wildcard Capture and Type-Preserving Operations

### 10.1. What Does the "capture of ?" Message Mean?

The following snippet often confuses learners:

```java
// Illustration with a compilation error; requires import java.util.List.
static void rewriteFirst(List<? extends Number> values) {
    // values.set(0, values.get(0));
}
```

If uncommented, the compiler reports an error involving `capture of ? extends Number`. In terms of intent, we are reading an element and writing it right back. However, the read type viewed through the upper bound is not automatically verified as the exact captured type required by the write call at another position.

Do not work around this with a raw `List`. When an operation is genuinely type-safe because it only reuses elements from the exact same list, you can give a name to the capture using a generic helper method.

### 10.2. A Helper Preserves the Same T for Both Reading and Writing

```java
// Declaration of two methods inside a class; requires import java.util.List.
static void swapFirstTwo(List<? extends Number> values) {
    swapCaptured(values);
}

private static <T extends Number> void swapCaptured(List<T> values) {
    if (values.size() < 2) {
        throw new IllegalArgumentException("need two elements");
    }

    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

Inside the helper, the type `T` links the element being read with the element being written. No arbitrary new `Number` is introduced into the list. It only swaps the positions of two elements that already belong to the same captured element type.

Even so, the method **does mutate the source**. The object must support `set`; passing an unmodifiable list can still throw `UnsupportedOperationException`. Wildcard capture solves type verification, not mutation permissions. [Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html)

### 10.3. Two Wildcards Do Not Mean the Same Type

If a method accepts two `List<? extends Number>` parameters, the unknown element type of each parameter may be different: one could be `Integer` and the other `Double`.

You cannot take an element from the first list and insert it into the second list just because both share the `Number` bound. Having the same upper bound does not mean having the same capture.

To transfer data between two collections, the signature must express a safe type relationship between source and destination. If you only need to read from both, this issue does not arise.

Capture conversion is formally specified in [JLS 5.1.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10).

## 11. Applying to Map and Nested Data Structures

### 11.1. Place the Wildcard Only on the Side That Needs Variance

```java
// Method declaration; requires import java.util.Map.
static double sumMappedValues(Map<String, ? extends Number> values) {
    double total = 0;
    for (Number value : values.values()) {
        total += value.doubleValue();
    }
    return total;
}
```

This method accepts `Map<String, Integer>` or `Map<String, Double>` because the value type is widened with an upper bound. The key type is still required to be `String`.

It does not become a map that allows `put("new", 1.5)`: the value to be written still belongs to an unknown type. Reading the result of `get` or `values` as `Number` is type-safe, though `null` values must still be accounted for.

If you only need the values and do not use the keys, you can accept `Collection<? extends Number>` and pass `map.values()`. Choose the parameter type according to the capabilities the algorithm actually needs. [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 11.2. An Outer Wildcard Does Not Automatically Make Every Level Covariant

`List<Integer>` is not a `List<Number>`, so nested data structures must be parameterized at each level.

For example, the intent "a group of collections, where each collection provides `Number` elements" can be expressed as:

```java
// Signature sketch, not a standalone program.
Collection<? extends Collection<? extends Number>> groups
```

The outer wildcard describes the inner collections; the inner wildcard describes the numeric elements of each inner collection.

There is no need to use this long signature if the problem only takes a flat collection. Nesting wildcards should stem from the data model, not from a habit of overcomplicating APIs.

## 12. Limitations Outside the Type System

An upper-bounded wildcard does not automatically handle the following concerns:

- **`null` source:** Calling methods on the source can still throw `NullPointerException`.
- **`null` elements:** Reading an element as `Number` does not guarantee that calling `doubleValue` is safe.
- **Empty source:** `get(0)` still requires a contract for when no elements are present.
- **Arithmetic:** Converting every `Number` to `double` can lose precision.
- **Concurrency:** Another reference may structurally modify the source during iteration.
- **Wrongly typed data from raw types:** A wildcard cannot restore type guarantees already broken across an unchecked boundary.
- **Ownership:** It does not create a copy or transfer mutation rights over the source.
- **Deep immutability:** It does not lock the internal state of element objects.

Therefore, the method signature is only part of the contract; documentation, validation, and data-handling policies must still match.

Do not cast `List<? extends Number>` to `List<Number>` to make `add` compile. A cast does not turn a `List<Integer>` into a list that can safely hold a `Double`.

## 13. Complete Program

Save as `UpperBoundedReadDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

public final class UpperBoundedReadDemo {
    private static double sum(Collection<? extends Number> values) {
        double total = 0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    private static Number first(List<? extends Number> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    private static <T> List<T> copySource(
            Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    private static void swapFirstTwo(List<? extends Number> values) {
        swapCaptured(values);
    }

    private static <T extends Number> void swapCaptured(List<T> values) {
        if (values.size() < 2) {
            throw new IllegalArgumentException("need two elements");
        }
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    private static double sumMappedValues(
            Map<String, ? extends Number> values) {
        double total = 0;
        for (Number value : values.values()) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Double> decimals = List.of(0.5, 1.5);
        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(decimals));

        List<? extends Number> source = integers;
        Number firstValue = first(source);
        System.out.println("First value: " + firstValue);

        integers.add(4);
        System.out.println("View after alias add: " + source);
        source.remove(0);
        System.out.println("After source remove: " + integers);

        List<Number> copy = copySource(source);
        copy.add(2.5);
        System.out.println("Copy: " + copy);
        System.out.println("Original: " + integers);

        List<Integer> pair = new ArrayList<>(List.of(10, 20));
        swapFirstTwo(pair);
        System.out.println("Captured swap: " + pair);

        List<Integer> toClear = new ArrayList<>(List.of(7, 8));
        Collection<? extends Number> unknownSubtype = toClear;
        unknownSubtype.clear();
        System.out.println("After wildcard clear: " + toClear);

        List<Integer> nullable = new ArrayList<>(List.of(9));
        List<? extends Number> nullAllowedByType = nullable;
        nullAllowedByType.add(null);
        System.out.println("Null insertion: " + nullable);

        Map<String, Integer> counts = Map.of("a", 2, "b", 3);
        System.out.println("Map value sum: " + sumMappedValues(counts));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked UpperBoundedReadDemo.java
java UpperBoundedReadDemo
```

The code has been verified against the Java 17 API baseline on a newer JDK with no unchecked warnings. The program does not mutate `List.of` lists; mutating operations use `ArrayList`.

Stdout:

```text
Integer sum: 6.0
Double sum: 2.0
First value: 1
View after alias add: [1, 2, 3, 4]
After source remove: [2, 3, 4]
Copy: [2, 3, 4, 2.5]
Original: [2, 3, 4]
Captured swap: [20, 10]
After wildcard clear: []
Null insertion: [9, null]
Map value sum: 5.0
```

### Explanation Across Key Learning Boundaries

- `sum` reads both `Integer` and `Double` sources through `Number`.
- `first` only returns a `Number` contract, so the receiving variable does not automatically become `Integer`.
- `source` observes the element added through `integers` because both references point to the same object.
- `source.remove(0)` compiles and mutates the source: a wildcard does not create immutability.
- `copySource` creates a new `List<Number>`; adding `2.5` to the copy does not alter the source structure.
- The capture helper swaps two elements within the same type `T` without casting.
- `clear` through a wildcard still empties a mutable source.
- `add(null)` is type-valid and accepted by `ArrayList`; afterward, this list is not passed to `sum`, which requires non-`null` elements.
- A wildcard on the map's value side allows reading an integer map through `Number`.

## 14. Common Mistakes and Fixes

| Practice | Problem | Fix |
| --- | --- | --- |
| Using `Collection<Number>` and expecting to accept `List<Integer>` | Lacks the desired subtype relationship | Use `? extends Number` for a read source |
| Interpreting `? extends Number` as allowing any `Number` to be added | The actual runtime element type may be narrower | Only read through the bound, or create a destination with an explicit type |
| Reading as `Integer` without checking | The source may contain a different `Number` subtype | Use the `Number` API or design a narrower type requirement |
| Treating a wildcard as an immutable collection | `remove`, `clear`, and aliases can still mutate it | Choose an unmodifiable view/copy mechanism and document ownership |
| Assuming `null` is blocked by a wildcard | `null` is valid for any reference type | Check the collection's value policy separately |
| Using raw types to silence capture errors | Loses type safety guarantees | Use a generic helper method when the relationship is genuinely safe |
| Moving elements between two wildcards with the same bound | The two captures may be different types | Express the source–destination relationship with a type parameter |
| Using wildcards for every return type | Pushes unnecessary complexity onto callers | Declare a sufficiently specific return type |
| Assuming wildcards handle emptiness or `null` | These are data conditions, not purely type issues | State and validate the input contract |
| Casting a source to `List<Number>` to add a `Double` | Can corrupt a backing `List<Integer>` (heap pollution) | Create a copy with an appropriate destination type |

## 15. Self-Check and Practice

### Questions

1. Does `Collection<? extends Number>` accept `Collection<Number>`?
2. Why does it also accept `Collection<Integer>` yet forbid `add(1)`?
3. How does reading an element as `Number` differ from casting it to `Integer`?
4. Can `clear` be called through a wildcard reference?
5. Is `add(null)` blocked at compile time, and what does it depend on at runtime?
6. Are two `List<? extends Number>` parameters guaranteed to have the same element type?
7. When do you need `<T extends Number>` instead of just a wildcard?
8. Does a capture helper turn an unmodifiable list into a modifiable one?
9. How does copying into a `List<Number>` differ from casting the source to that type?
10. What data constraints must an algorithm using `doubleValue` still document?

### Exercises

- Write a method that counts how many elements have a positive `doubleValue()`, accepting `Collection<? extends Number>` without mutating the source.
- Pass a `List<Integer>`, a `List<Double>`, and a `List<Number>` to the same method.
- Add a `source.add(1)` line in a test snippet to observe the compiler error; explain it in terms of the unknown element type.
- Demonstrate with a small example that mutating through an alias is observable through a wildcard variable.
- Create a `List<Number>` copy from an integer source and add a floating-point number to the copy.
- Call the swap helper with an `ArrayList`, then try an unmodifiable list to distinguish compile-time type errors from runtime operation errors.
- Write two methods that retrieve the first element: one returning `Number`, and a generic one returning `T`; compare the receiving variable types at the call site.
- Given a map with `String` keys and integer values, write a method that reads the values through a `Number` upper bound.

### Reference Answers

1. Yes; the upper bound includes `Number` itself.
2. It accepts a concrete subtype, but the compiler does not know which specific subtype it is at the write site.
3. The upper bound guarantees every element can be used as a `Number`; it does not guarantee any particular subtype.
4. It is callable from a type-checking standpoint; at runtime, the underlying object must support the operation.
5. It is valid at compile time; at runtime, the object must support additions and permit `null` elements.
6. No; one source could be `Integer` while the other is `Double`.
7. When you need to preserve a type relationship across multiple positions, especially with the return type.
8. No; it only helps prove the type relationship for the method call.
9. A copy has its own structure and explicit destination type; a cast does not change the underlying source object.
10. Non-`null` source and elements, empty collection handling, numeric precision, and concurrent modification rules.
