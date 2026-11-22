# Writing a Maximum-Element Function with a Comparable Bound in Java Generics

## 1. Goal and Problem Statement

Suppose you need to select the largest element in a group of data:

- Integers: from `[3, 9, 7]`, select `9`.
- Strings: from `["An", "Mai", "Binh"]`, select `"Mai"` according to String's natural ordering.
- Dates: select the latest date among multiple `LocalDate` values.
- Domain objects: select the `Ticket` with the highest priority, if the class defines a natural ordering.

Writing separate `maxInteger`, `maxString`, and `maxDate` methods duplicates the algorithm. Generics allow you to write **a single max-selection function**, while requiring the compiler to verify that elements can be compared under the same rule.

Core idea:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values) {
    // Iterate and keep the largest value seen.
}
```

This is not yet a complete method body; the runnable Java 17 program in section 10 contains the full implementation, handling both empty input and `null`.

After this lesson, you will understand:

1. What `Comparable<T>` is and what `compareTo` means.
2. Why `<T extends Comparable<? super T>>` is necessary for a generic max function.
3. The differences between `Comparable<T>`, `Comparable<? super T>`, and `Comparator<? super T>`.
4. Why we must check empty/null inputs, use `compareTo > 0`, and keep the winning element on ties.
5. How to choose the input source type: `List<T>`, `Collection<? extends T>`, or `Iterable<? extends T>`.
6. How to interpret type inference/bounds errors when calling the function with non-comparable types or mixed types.
7. How to test, analyze complexity, and compare with `Collections.max`/`Stream.max`.

## 2. Algorithmic Thinking Before Adding Generics

A simple solution for a list of integers:

```java
static Integer maxInteger(List<Integer> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty input");
    }
    Integer best = values.get(0);
    for (Integer value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

The sample method above requires importing `java.util.List` and assumes non-null elements. One point we can improve: because the loop starts from the beginning of the list, the first value is compared against itself on the first iteration. That does not produce the wrong result under normal comparison rules, but it is unnecessary. In the complete implementation, we take the first element via an iterator and then iterate over **the remaining elements**.

Algorithm:

1. If there are no elements, max cannot be determined: handle the empty case according to the contract.
2. Take the first element as `best`.
3. For each subsequent element `candidate`, compare `candidate.compareTo(best)`.
4. If the result is greater than 0, update `best = candidate`.
5. When finished, return `best`.

**Loop invariant:** after processing the first k elements, `best` is a largest element among those k elements according to the defined ordering. Each new element either beats `best` or does not; therefore after n elements, `best` is a largest value overall.

If multiple elements compare equal (result 0), using the `> 0` operator keeps **the first largest element encountered**. This is a stable policy when picking at most one value; it does not mean every implementation of max is required to have the same tie-breaking policy.

## 3. `Comparable<T>`: Natural Ordering Defined by the Object

Java declares an interface for comparability:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

The signature above is an abridged form to show the core method of the standard interface, not a request to rewrite `java.lang.Comparable` in your project.

A class implementing `Comparable<T>` defines the **natural ordering** of its objects:

```java
record Ticket(String id, int priority) implements Comparable<Ticket> {
    @Override
    public int compareTo(Ticket other) {
        return Integer.compare(priority, other.priority);
    }
}
```

Under this rule, a ticket with a higher `priority` is considered larger. `id` serves to identify the ticket and **does not participate in comparison**. Two tickets with different ids but the same priority are considered equal according to compareTo.

### Sign convention of `compareTo`

| Result of `x.compareTo(y)` | Meaning |
| --- | --- |
| Negative (`< 0`) | x precedes y; x is less than y under natural ordering. |
| Zero (`0`) | x and y are equivalent with respect to comparison order. |
| Positive (`> 0`) | x follows y; x is greater than y. |

**Do not assume `compareTo` only returns -1, 0, or 1.** The API only promises negative/0/positive signs. Standard classes, for example, can return various negative/positive values. Therefore check `candidate.compareTo(best) > 0`, not `== 1`.

### When is `compareTo` inappropriate?

Some objects do not have a sensible natural ordering, or have multiple comparison criteria depending on business needs. For example, an employee might be sorted by salary, start date, or name. In that case, do not force the class to implement an arbitrary natural ordering; pass in a `Comparator<T>`, as shown in section 13.

## 4. Why Declare the Bound `T extends Comparable...`?

Try writing:

```java
// Invalid if the body calls compareTo:
static <T> T max(List<T> values) {
    T candidate = values.get(0);
    T best = values.get(1);
    if (candidate.compareTo(best) > 0) {
        return candidate;
    }
    return best;
}
```

The error is at `candidate.compareTo`: the compiler only knows T is an unbounded reference type, roughly like Object. `Object` does not declare `compareTo`, so there is no proof that every T supports that method.

How to add the constraint to the generic method:

```java
static <T extends Comparable<T>> T maxSimple(List<T> values) {
    // T knows how to compareTo(T).
    return values.get(0);
}
```

`extends` in a **type parameter bound** is used for both classes and interfaces. `T extends Comparable<T>` does not force T to be a concrete subclass of Comparable: `Comparable` is an interface, and `extends` simply expresses a type bound.

The bound lets the compiler know a T has `int compareTo(T)`. A type-safe signature does not merely return "any T" — it also requires **comparability**.

### A bound is a compile-time requirement, not a runtime cast

When a caller writes `max(List.of(3, 9, 7))`, the compiler can infer T as Integer; Integer implements Comparable<Integer>, so it is valid.

If the caller passes `new Object()` instances:

```java
// Does not compile:
Object result = max(List.of(new Object(), new Object()));
```

`Object` does not implement Comparable<Object> or a compatible Comparable. The compiler rejects it at the call site. That is far better than waiting until runtime and performing an unchecked cast to Comparable.

## 5. A More Flexible Bound: `Comparable<? super T>`

An API should generally be written as:

```java
<T extends Comparable<? super T>>
```

instead of only:

```java
<T extends Comparable<T>>
```

The reason is that a subclass can **inherit comparability from its superclass**, without directly implementing Comparable for the subclass itself.

Example:

```java
static class Score implements Comparable<Score> {
    final int points;

    Score(int points) {
        this.points = points;
    }

    @Override
    public int compareTo(Score other) {
        return Integer.compare(points, other.points);
    }
}

static final class BonusScore extends Score {
    BonusScore(int points) {
        super(points);
    }
}
```

`Score` implements `Comparable<Score>`. `BonusScore` inherits `Score.compareTo(Score)` and can therefore compare `BonusScore` instances (since BonusScore is a Score). However, `BonusScore` does not need to implement `Comparable<BonusScore>` separately.

If the max function required `T extends Comparable<T>`, a call retaining the result type `BonusScore` might fail type inference:

```java
// Error example with an overly strict signature:
static <T extends Comparable<T>> T maxTooStrict(List<T> list) {
    return list.get(0);
}

// BonusScore chosen = maxTooStrict(List.of(
//         new BonusScore(10), new BonusScore(20)));
```

The `maxTooStrict` method in this example simply returns the first element to isolate the **bound** error. This case was verified with JDK 17: the compiler reports `inference variable T has incompatible bounds` when the target type is BonusScore.

Meanwhile, the bound `Comparable<? super T>` accepts a Comparable of T **or of a supertype that T inherits from**. With T=BonusScore, Comparable<Score> fits because Score is a supertype of BonusScore. The wider signature remains soundly typed:

```java
static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

Because `compareTo` can accept Score, passing a BonusScore into it is completely valid.

### Reading the syntax from inside out

```text
<T extends Comparable<? super T>>
                 |          |
           comparability   compareTo parameter type
                           can be T or a supertype of T
```

This is a **lower-bounded wildcard**. For a place that **consumes** T (the parameter of compareTo), accepting a supertype of T enables reusing the superclass's comparison capability. This connects to the PECS principle: **Consumer Super**.

### Do not confuse `Comparable<? super T>` with `Comparable<? extends T>`

`compareTo` **accepts** a value as input. If the comparator only accepted an unknown subtype of T, the compiler would have no guarantee that an arbitrary T could be passed into it. With `? super T`, any T can be used in the input position.

## 6. Choosing the Input Parameter: List, Collection, or Iterable?

A simple version might accept `List<T>`:

```java
static <T extends Comparable<? super T>> T max(List<T> list) {
    // ...
}
```

But the algorithm only needs **sequential traversal**. It does not need `get(index)`, `set`, `sort`, `size`, or list mutation. Therefore `Iterable<? extends T>` is an appropriately general contract:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

Benefits:

- Works with List and Set, or domain-specific iterables.
- Does not require an indexable structure.
- Does not mutate the input; the method only reads each element.
- Accepts sources whose elements are subtypes of T thanks to `? extends T`.
- Callers still receive the exact type T inferred by the compiler from the source and context.

`Iterable<? extends T>` is a producer of T; this is **Producer Extends**. Combined with `Comparable<? super T>`, we have both PECS ideas in a single signature:

- **Element source:** `? extends T` because data is read from the source.
- **Comparability:** `? super T` because compareTo consumes a T value.

**Why not use `List<? super T>` as input?** A list whose element type is a supertype of T could contain objects that are not T, so reading from it as T is not guaranteed.

### Is `Iterable` always needed?

No. If the API needs `size()` or uses `Collection` features, choose `Collection<? extends T>`. If random access by index is needed for a specific algorithmic goal, `List<? extends T>` also makes sense. The goal is **the narrowest interface expressive enough for the usage requirements**, not using Iterable out of habit.

## 7. Proper Implementation: Single-Pass Traversal with Iterator

Recommended implementation:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values) {
    Objects.requireNonNull(values, "values");

    Iterator<? extends T> it = values.iterator();
    if (!it.hasNext()) {
        throw new IllegalArgumentException("empty input");
    }

    T best = Objects.requireNonNull(it.next(), "element");

    while (it.hasNext()) {
        T candidate = Objects.requireNonNull(it.next(), "element");
        if (candidate.compareTo(best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

To place this inside a class, import `java.util.Iterator` and `java.util.Objects`. The complete program in section 10 includes the imports and main.

Step-by-step breakdown:

1. `Objects.requireNonNull(values,"values")` rejects a null iterable reference up front.
2. `values.iterator()` obtains an iterator; the method needs no knowledge of the concrete collection.
3. `!it.hasNext()` handles empty input with a clear `IllegalArgumentException`.
4. `it.next()` retrieves the first element as best; checks for a null element.
5. Each remaining element is null-checked and then compared against best.
6. `candidate.compareTo(best) > 0` updates best when candidate is greater.
7. Returns directly **one of the objects present in the input**, without creating copies.

### Why not initialize `T best = null`?

Doing so requires extra rules for the first element and can mask null bugs. Taking the first element as best after checking for emptiness keeps the invariant clean: when entering the loop, best is an actual element of the set and non-null.

### Why not compare with `==` or `>`?

Generic T is a reference type; the `>` operator is not defined for arbitrary objects of type T. `==` compares object identity (aside from relevant primitive/boxing situations), not ordering. `compareTo` is the comparison contract guaranteed by the compiler.

### Why not use `>= 0`?

Using `>= 0` also picks a largest element if the ordering is valid, but when two elements are equivalent (compareTo returns 0), it picks **the later element** instead of keeping the first one. The pattern above uses `> 0` as a fixed, easily testable tie-breaking rule.

### Handling null in the contract

Here every element is required to be non-null. When encountering a null element, the method throws `NullPointerException("element")`. If an API wants null as a minimum/maximum value, it must define an ordering for null and should typically use `Comparator.nullsFirst`/`Comparator.nullsLast` in a Comparator-accepting overload. Never let null slip into `compareTo` without a clear policy.

### What if the source is modified during iteration?

The method does not synchronize the collection. If another thread modifies the collection during traversal, the outcome depends on the collection's iterator contract; `ConcurrentModificationException` or other collection-specific behavior may occur. In concurrent code, use a snapshot or proper synchronization rather than relying on generic bounds to solve concurrency.

## 8. Complexity and Correctness

For n elements:

- Reading the first element as best: O(1).
- Comparing the remaining elements: exactly **n-1 calls to compareTo** when n ≥ 1 (excluding null checks and iteration overhead).
- Time: O(n) if each compareTo call is O(1). More generally: O(n × comparison cost).
- Auxiliary memory of the algorithm: O(1), excluding the iterator and existing structures in the source. It only holds best, candidate, and the iterator.

It is impossible to determine the max in the general case while skipping an unexamined element: an unexamined element could be larger than all elements seen so far.

### Proof of the invariant

**Initialization:** After reading the first element, best is clearly the largest in the set consisting solely of that element.

**Maintenance:** Suppose best is largest among the k elements processed so far. Consider the next candidate:

- If `candidate.compareTo(best)>0`, candidate is greater than best and therefore not smaller than any preceding element.
- If the condition does not hold, best is not less than candidate under the expected comparison order; it continues to be a largest element among the k+1 elements.

**Termination:** After traversing all n elements, best is a largest element.

The proof relies on `compareTo` obeying a **consistent ordering and the Comparable contract**. If compareTo violates transitivity or changes results based on unstable state, the notion of largest element may become ill-defined and the loop cannot guarantee the intended meaning.

## 9. Convenience Multi-Argument Form: `maxOf`

Instead of building a List manually, a caller may want:

```java
int best = maxOf(5, 2, 8, 4);
```

A varargs overload/utility method:

```java
@SafeVarargs
public static <T extends Comparable<? super T>> T maxOf(
        T first, T... rest) {
    T best = Objects.requireNonNull(first, "first");
    for (T candidate : rest) {
        T checked = Objects.requireNonNull(candidate, "element");
        if (checked.compareTo(best) > 0) {
            best = checked;
        }
    }
    return best;
}
```

`maxOf` has a mandatory `first` element, so callers cannot invoke it with zero arguments. Inside, it does not return the varargs array, does not store a reference to the array, and does not write an incompatible type into any slot; it only iterates and picks best. In Java 17, `@SafeVarargs` is valid on static varargs methods and suppresses generic varargs warnings based on the author's safety guarantee.

**Important:** The annotation does not make code safe by itself. If you later refactor the method to retain, publish, or improperly write to the varargs array, you must re-evaluate the `@SafeVarargs` guarantee. Especially when T is non-reifiable, do not expose `T[] rest` externally lightly.

### Can `maxOf("A", "B")` be used?

Yes, because String implements Comparable<String>. But do not confuse a single invocation sharing T with the ability to compare arbitrary disparate types. `maxOf("A", 3)` will not necessarily infer a T satisfying the Comparable bound, even though String and Integer are individually Comparable.

### Note on overloading

If an API has both `max(List<T>)` and `maxOf(T, T...)`, giving the varargs version a distinct name `maxOf` as above avoids confusing overload resolution with arrays and generics, while signaling a non-empty contract at the call site.

## 10. Complete Runnable Java 17 Program

**File `ComparableMaxDemo.java`**:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class ComparableMaxDemo {
    public static <T extends Comparable<? super T>> T max(
            Iterable<? extends T> values) {
        Objects.requireNonNull(values, "values");
        Iterator<? extends T> it = values.iterator();
        if (!it.hasNext()) {
            throw new IllegalArgumentException("empty input");
        }
        T best = Objects.requireNonNull(it.next(), "element");
        while (it.hasNext()) {
            T candidate = Objects.requireNonNull(it.next(), "element");
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    @SafeVarargs
    public static <T extends Comparable<? super T>> T maxOf(
            T first, T... rest) {
        T best = Objects.requireNonNull(first, "first");
        for (T candidate : rest) {
            T checked = Objects.requireNonNull(candidate, "element");
            if (checked.compareTo(best) > 0) {
                best = checked;
            }
        }
        return best;
    }

    public static <T> T maxBy(
            Iterable<? extends T> values, Comparator<? super T> comparator) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(comparator, "comparator");
        Iterator<? extends T> it = values.iterator();
        if (!it.hasNext()) {
            throw new IllegalArgumentException("empty input");
        }
        T best = Objects.requireNonNull(it.next(), "element");
        while (it.hasNext()) {
            T candidate = Objects.requireNonNull(it.next(), "element");
            if (comparator.compare(candidate, best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    record Ticket(String id, int priority) implements Comparable<Ticket> {
        @Override
        public int compareTo(Ticket other) {
            return Integer.compare(priority, other.priority);
        }
    }

    static class Score implements Comparable<Score> {
        final String label;
        final int points;

        Score(String label, int points) {
            this.label = label;
            this.points = points;
        }

        @Override
        public int compareTo(Score other) {
            return Integer.compare(points, other.points);
        }

        @Override
        public String toString() {
            return label + ":" + points;
        }
    }

    static final class BonusScore extends Score {
        BonusScore(String label, int points) {
            super(label, points);
        }
    }

    public static void main(String[] args) {
        System.out.println("integers=" + max(List.of(3, 9, 7)));
        System.out.println("strings=" + max(List.of("An", "Mai", "Binh")));
        System.out.println("dates=" + max(List.of(
                LocalDate.of(2026, 1, 3),
                LocalDate.of(2026, 1, 10))));
        System.out.println("varargs=" + maxOf(5, 2, 8, 4));

        List<Ticket> tickets = List.of(
                new Ticket("first", 5),
                new Ticket("second", 5),
                new Ticket("low", 3));
        System.out.println("tie=" + max(tickets).id());

        List<BonusScore> bonuses = List.of(
                new BonusScore("Bronze", 10),
                new BonusScore("Gold", 20));
        BonusScore bestBonus = max(bonuses);
        System.out.println("inheritedComparable=" + bestBonus);

        System.out.println("customComparator=" + maxBy(
                List.of("An", "Huyen", "Lan"),
                Comparator.comparingInt(String::length)));
        System.out.println("jdkMax=" + Collections.max(List.of(3, 9, 7)));

        try {
            max(List.<Integer>of());
        } catch (IllegalArgumentException e) {
            System.out.println("empty=" + e.getMessage());
        }

        try {
            max(Arrays.asList(1, null, 3));
        } catch (NullPointerException e) {
            System.out.println("null=" + e.getMessage());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 -Xlint:all ComparableMaxDemo.java
java ComparableMaxDemo
```

**Verified exact stdout:**

```text
integers=9
strings=Mai
dates=2026-01-10
varargs=8
tie=first
inheritedComparable=Gold:20
customComparator=Huyen
jdkMax=9
empty=empty input
null=element
```

The command `javac --release 17 -Xlint:all` compiled this program without any warnings in testing.

### Interpreting the output

- `integers=9`: Integer implements Comparable<Integer>, picking 9.
- `strings=Mai`: String has lexicographical order according to `String.compareTo`; in this dataset Mai follows An and Binh. This does not mean String.compareTo understands Vietnamese collation or user locale casing.
- `dates=2026-01-10`: LocalDate compares chronologically.
- `varargs=8`: `maxOf` finds the largest element among the integer arguments.
- `tie=first`: two Tickets with priority=5 compare as 0; using `>0` retains the first element.
- `inheritedComparable=Gold:20`: BonusScore inherits Comparable<Score> from Score and is accepted by the `Comparable<? super T>` bound.
- `customComparator=Huyen`: comparator by string length chooses Huyen (5 characters) instead of String's natural ordering.
- `jdkMax=9`: standard library result matches our custom implementation.
- `empty=empty input`: demo deliberately throws IllegalArgumentException with a consistent message.
- `null=element`: demo deliberately rejects null elements in the source.

## 11. Compilation Error Example 1: T Is Not Comparable

**File `NonComparableMax.java` — intentionally fails to compile:**

```java
import java.util.List;

class NonComparableMax {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        return values.get(0);
    }

    static void test() {
        Object result = max(List.of(new Object(), new Object()));
    }
}
```

Command:

```bash
javac --release 17 -Xdiags:verbose NonComparableMax.java
```

The compiler reported the key diagnostic:

```text
method max in class NonComparableMax cannot be applied to given types
required: List<T>
found:    List<Object>
reason: inference variable E has incompatible bounds
upper bounds: Comparable<? super T>,Object
lower bounds: Object
```

`Object` does not provide the required Comparable. Do not cast `Object` to Comparable just to silence the compiler if the actual objects are not comparable. Design a type with a natural ordering or use an externally supplied comparator.

## 12. Compilation Error Example 2: Overly Strict Bound

**File `WrongComparableBound.java` — intentionally fails to compile:**

```java
import java.util.List;

class WrongComparableBound {
    static <T extends Comparable<T>> T max(List<T> values) {
        return values.get(0);
    }

    static class Base implements Comparable<Base> {
        @Override
        public int compareTo(Base other) {
            return 0;
        }
    }

    static class Child extends Base {}

    static void test() {
        Child result = max(List.of(new Child(), new Child()));
    }
}
```

Java 17 compiler reports:

```text
incompatible types: inference variable T has incompatible bounds
equality constraints: Base,E
upper bounds: Child,Object,Comparable<T>
```

`Child` inherits `Comparable<Base>`, not `Comparable<Child>` as required by the strict bound. The method signature, when only compareTo is needed, can be fixed to:

```java
static <T extends Comparable<? super T>> T max(List<T> values) {
    // Use the real max algorithm as in section 7.
    return values.get(0);
}
```

The snippet above only illustrates the **corrected bound signature**, not a full max implementation. With this bound, the caller can receive Child back when the source elements are all Child.

**Do not "fix" this by forcing Child to implement Comparable<Child> separately** if that does not fit the inheritance model. Using `? super T` lets the API respect the Comparable<Base> that the subclass already has.

## 13. Compilation Error Example 3: Mixing Types Without a Common Ordering

**File `MixedTypesMax.java` — intentionally fails to compile:**

```java
import java.util.List;

class MixedTypesMax {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        return values.get(0);
    }

    static void test() {
        Object result = max(List.of("A", 3));
    }
}
```

The compiler reported `method max cannot be applied` and `inference variable E has incompatible bounds`, with constraints from String, Integer, and Comparable.

Each String or Integer can compare with objects of **its own compatible family**, but that does not mean String and Integer share a common natural ordering usable by `compareTo`. The condition must guarantee compatibility across the whole set, not merely each element in isolation.

If business logic truly needs to compare heterogeneous data, you must define **a clear common rule** and use an appropriate Comparator. For example, convert both to a domain type with a unified comparison criterion, or compare only by a meaningful measurable property. Do not force disparate types into raw Comparable and guess the outcome.

## 14. Compilation Error Example 4: Unnecessary Number Bound

**File `WrongNumberBound.java` — intentionally fails to compile:**

```java
import java.util.List;

class WrongNumberBound {
    static <T extends Number & Comparable<? super T>> T max(
            List<T> values) {
        return values.get(0);
    }

    static void test() {
        String result = max(List.of("A", "B"));
    }
}
```

The compiler reports `incompatible bounds`, including:

```text
upper bounds: Number,Comparable<? super T>,Object
lower bounds: String
```

String has Comparable<String> but **does not extend Number**. If the algorithm only calls compareTo, the Number constraint is redundant and excludes valid types like String, LocalDate, suitable enums, or Comparable domain classes.

When is the Number bound useful? When the body **genuinely needs Number methods** such as `doubleValue()` alongside compareTo. Then:

```java
<T extends Number & Comparable<? super T>>
```

is appropriate because it expresses **two requirements**. With multiple bounds, the class bound `Number` must precede the interface bound `Comparable`.

## 15. Comparison with the Standard Library

Java already provides max-selection APIs; writing one yourself is for understanding Generics, bounds, and invariants, not because every project needs a custom utility.

### `Collections.max`

`java.util.Collections.max(Collection<? extends T>)` uses natural ordering and a type parameter bound closely matching `Comparable<? super T>`; the API also retains bound details for binary compatibility. You can write:

```java
Integer best = Collections.max(List.of(3, 9, 7));
```

Requires importing `java.util.Collections`. `Collections.max` requires a non-empty collection; on empty input, the standard API throws `NoSuchElementException`, **unlike** the IllegalArgumentException deliberately chosen by our custom `max`. Check the exception contract when replacing a custom implementation with the standard API.

`Collections.max(collection, comparator)` also has an overload accepting a Comparator for external ordering.

### `Stream.max`

With streams:

```java
Optional<Integer> best =
        List.of(3, 9, 7).stream().max(Integer::compareTo);
```

`Stream.max(Comparator)` returns `Optional<T>`, so an empty stream can yield Optional.empty() instead of forcing an exception. If the application wants callers to handle the absent-element case, `Optional<T>` is a useful contract. Never call `optional.get()` unconditionally on an empty Optional.

### Write your own or use the library?

Use `Collections.max` or `Stream.max` when their behavior satisfies your contract. Write your own when you need to:

- Teach or study type bounds, iterators, and generic inference.
- Specify custom handling for null, empty input, and tie-breaking.
- Support an Iterable where Collection/Stream APIs are not directly provided.
- Integrate logging, comparison checks, or domain-specific handling.

Do not rewrite just to feel "more generic": weigh maintenance cost against standard API guarantees.

## 16. Comparator: Extending When T Has No Natural Ordering

The Comparable bound requires **T itself to have a natural ordering**. Many data types do not or should not have a default order. In such cases, pass in a Comparator:

```java
public static <T> T maxBy(
        Iterable<? extends T> values,
        Comparator<? super T> comparator) {
    Objects.requireNonNull(values, "values");
    Objects.requireNonNull(comparator, "comparator");
    Iterator<? extends T> it = values.iterator();
    if (!it.hasNext()) {
        throw new IllegalArgumentException("empty input");
    }
    T best = Objects.requireNonNull(it.next(), "element");
    while (it.hasNext()) {
        T candidate = Objects.requireNonNull(it.next(), "element");
        if (comparator.compare(candidate, best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

Requires importing `Comparator`, `Iterator`, and `Objects`. This snippet is included in the complete program in section 10.

Example:

```java
String longest = maxBy(
        List.of("An", "Huyen", "Lan"),
        Comparator.comparingInt(String::length));
System.out.println(longest); // Huyen
```

Here T does not need to extend Comparable because the comparator takes responsibility for comparison. `Comparator<? super T>` uses super because the comparator **consumes** two T objects.

### Natural ordering vs. custom ordering

- `max(List.of("An","Huyen","Lan"))` uses `String.compareTo`; the result follows natural Unicode order, not length.
- `maxBy(..., comparingInt(String::length))` uses string length; Huyen is longest in the example.
- If multiple strings have the same length, this code keeps the first string with the maximum length, because it only updates when comparison is positive.

### What effect does `Comparator.reversed()` have?

If a comparator defines `a < b` according to a criterion, calling `reversed()` flips the order. Calling max with the reversed comparator yields the equivalent of **the minimum element according to the original comparator**, by the sign logic of compare.

Do not flip the comparison direction inside the body arbitrarily. Keeping the invariant "candidate > best according to the supplied comparator" prevents bugs when adding ascending/descending modes.

## 17. Writing `compareTo` Properly for Domain Classes

An excerpt from `Ticket`:

```java
record Ticket(String id, int priority) implements Comparable<Ticket> {
    @Override
    public int compareTo(Ticket other) {
        return Integer.compare(priority, other.priority);
    }
}
```

### Avoid subtraction as a comparator

Pattern prone to overflow:

```java
// AVOID:
return this.priority - other.priority;
```

If one number is near `Integer.MAX_VALUE` and the other is near `Integer.MIN_VALUE`, subtraction can overflow and invert the sign incorrectly. Using `Integer.compare(this.priority, other.priority)` or `Comparator.comparingInt(Ticket::priority)` is clearer and sign-safe.

### The `Comparable` contract

A healthy ordering must satisfy properties such as:

- The sign of `x.compareTo(y)` must be opposite to the sign of `y.compareTo(x)`.
- If x > y and y > z, then x must be > z by transitivity.
- If x.compareTo(y)==0, the comparison relations of x and y with any z must agree to preserve ordering consistency.
- Consider the `null` policy; many standard Comparable implementations reject null.

**Consistency with `equals` is recommended, though not always mandatory.** For instance, Ticket is a record: equals checks both id and priority, whereas compareTo checks only priority. Two Tickets with different ids but equal priority are treated as equivalent by compareTo. `max` can still pick a largest element, but when using such a type in `TreeSet`/`TreeMap`, comparison-based collections may treat them as duplicate keys. Consider business identity and collection semantics carefully.

### Ordering based on mutable state

If an object's priority changes during comparison, the max result may fail to reflect a consistent snapshot. Define immutable data or coordinate state updates appropriately when using comparators in algorithms or sorted collections.

## 18. Semantics of String, Number, LocalDate, and null

### String

`String.compareTo` compares strings lexicographically based on UTF-16 code units. It does not replace a `Collator` for language-specific ordering. Thus the String max result is **greatest under String's natural ordering**, not "last name in a Vietnamese directory."

If locale-aware user ordering is needed, choose an appropriate comparator rather than arbitrarily altering the input data.

### Integer, Long, and Number

`Integer` and `Long` are both Comparable, but they do not share a common `Comparable<Number>` contract. A List<Number> containing both Integer and Long does not automatically have a shared natural ordering. Adding `T extends Number & Comparable<? super T>` does not make all Number subclasses mutually comparable.

You can build a comparator handling Number via a defined quantity like `doubleValue()`, but watch out for precision loss, NaN, and domain-specific Number types. Never convert to double without checking calculation requirements.

### Float/Double

`Float.compareTo`/`Double.compareTo` define an ordering covering `NaN` and signed zero per the class contract. Do not use the `>` operator directly assuming it matches `compareTo` for all special floating-point values.

### LocalDate

`LocalDate` has a date-based natural ordering, so `max(List<LocalDate>)` chooses the latest date. If handling events with time and timezone, choose a domain type like `Instant`, `ZonedDateTime`, or a suitable concrete comparator rather than comparing LocalDate and mistaking it for "latest timestamp."

### Null

The demo API deliberately rejects null for both the container and elements. `Objects.requireNonNull` makes the failure point explicit instead of letting compareTo throw at an unpredictable point. If null carries domain meaning (such as "not yet rated"), define an explicit order via Comparator or filter nulls before calling max, and state this in the contract.

## 19. Edge Cases and Test Matrix

| Input | Expected result with section 7 implementation | Explanation |
| --- | --- | --- |
| `[3,9,7]` | 9 | Largest element. |
| `[4]` | 4 | Single element is also max. |
| `[5,5,3]` | First 5 element | Keeps best when compareTo returns 0. |
| `[]` | IllegalArgumentException | No first element to pick. |
| `null` as Iterable | NullPointerException, message `values` | Guard at top of method. |
| `[1,null,3]` | NullPointerException, message `element` | Contract rejects null elements. |
| `["An","Mai","Binh"]` | "Mai" | Natural String order. |
| `List<BonusScore>` | Highest-scoring BonusScore | Wildcard super bound accepts Comparable<Score>. |
| `List<Object>` | Compile error at invocation | Object does not guarantee Comparable. |
| Mixed `List` of `String,Integer` | Cannot infer common natural max | Incompatible comparison families. |

Not all data representable by `List<?>` has a natural max. The compiler needs a compatible bound across all elements statically; working around it with raw/unchecked casts forfeits that guarantee.

### Testing correctness rather than only happy-path examples

- Max at start/end/middle of input.
- Multiple elements tied in order.
- Negative values or large numbers when using numeric data.
- Null elements and null container.
- Empty input and single-element input.
- Subclasses inheriting Comparable from a parent.
- Reversed comparator or mismatched comparator.
- Mutation/concurrency when the source is a shared mutable collection.

When requirements change the selection rule (e.g., returning all elements tied for max), the API's return type must change; a method returning T cannot return all tied elements without changing its contract.

## 20. Common Misconceptions

**Misconception 1: "A generic T can call compareTo without a bound."** Incorrect; the compiler only knows methods guaranteed by T's bound. Add `extends Comparable<? super T>` if natural ordering is required.

**Misconception 2: "The bound must be Comparable<T>, without wildcards."** Incorrect. `Comparable<? super T>` is more flexible and safer for subclasses inheriting Comparable from a parent class.

**Misconception 3: "Comparable<? super T> lets you compare any two Object types."** Incorrect. It only establishes the ability to pass a T into an appropriate compareTo; it does not create a common ordering between String and Integer.

**Misconception 4: "compareTo returns +1 when greater."** Incorrect; only a positive sign is required. Check `>0`.

**Misconception 5: "You must cast T to Comparable in the body."** Unnecessary once the proper bound is declared; raw casts weaken type safety.

**Misconception 6: "Use List<Number> to accept List<Integer> because Integer extends Number."** Generics are invariant. Read from List<Integer> via `List<? extends Number>` or copy into a new List<Number>.

**Misconception 7: "No need to handle empty input."** A method returning T has no element to return when empty. Throw an exception or change the contract to Optional<T>.

**Misconception 8: "Which tied element max returns doesn't matter."** For objects with different identities where compareTo=0, tie-breaking can affect the returned id, business logic, and tests.

**Misconception 9: "String max sorts alphabetically in Vietnamese."** String.compareTo does not provide locale-aware collation.

**Misconception 10: "Having Comparable means equals must match compareTo."** Recommended for many use cases, though not mandatory. When inconsistent, sorted collections have semantics you must watch out for.

**Misconception 11: "Using a comparator is merely a syntactic difference."** Comparator enables strategy-based ordering, even for classes that do not implement Comparable. It broadens the algorithm's applicability.

**Misconception 12: "Silencing warnings with @SuppressWarnings fixes everything."** Annotations do not make Object Comparable or produce a consistent ordering, and they do not fix compile errors about incompatible bounds.

## 21. Practice Exercises with Answers

### Exercise 1. Fill in the bound

Given the body:

```java
static <T /* bound? */> T bigger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

**Answer:** `<T extends Comparable<? super T>>`. The bound ensures `a.compareTo(b)` is valid. Using `>=0` returns a on a tie; using `>0` with else b returns b on a tie.

### Exercise 2. Why not write `candidate > best`?

**Answer:** The `>` operator does not apply to arbitrary reference types T. Java does not overload `>` for arbitrary objects; `compareTo` or a Comparator is required.

### Exercise 3. What is the difference between `Comparable<T>` and `Comparable<? super T>`?

**Answer:** The second bound allows T to implement Comparable for a supertype of T, which is useful for subclasses like BonusScore inheriting `Comparable<Score>`. This is a safe relaxation at the compareTo parameter position.

### Exercise 4. Why is `List.of("A", 3)` invalid for natural max?

**Answer:** String and Integer each have their own natural ordering, with no guarantee of a common T satisfying Comparable<? super T> for both under the signature. The compiler reports incompatible bounds.

### Exercise 5. Why can a List of Integer be passed to Iterable<? extends Number>?

**Answer:** Because Iterable produces elements for reading, and Integer extends Number. However, to return max with T=Number, Number itself would need a matching Comparable; the Iterable relationship alone does not satisfy the Comparable bound.

### Exercise 6. Why check for empty input?

**Answer:** No first element exists to serve as best; a method returning T must choose a policy, such as IllegalArgumentException, or switch to Optional<T>.

### Exercise 7. Which element does the max function in section 7 pick on a tie?

**Answer:** It keeps the first largest element because it only replaces best when compareTo > 0. Changing it to >= 0 would make a later tied element replace the earlier one.

### Exercise 8. Can max be used on a Ticket record?

**Answer:** Yes, if Ticket implements Comparable<Ticket> with a valid compareTo. The section 10 example compares by priority and picks the first Ticket when two share priority 5.

### Exercise 9. Why not write `this.priority - other.priority`?

**Answer:** Integer subtraction can overflow and flip the sign erroneously; use `Integer.compare`.

### Exercise 10. How does `Collections.max` differ from our custom function?

**Answer:** Same natural-max goal on a compatible collection, but our custom example accepts Iterable and chooses IllegalArgumentException when empty; Collections.max throws NoSuchElementException on an empty collection.

### Exercise 11. What if a class lacks Comparable and you want to select by age?

**Answer:** Use `maxBy(values, Comparator.comparingInt(Person::age))` given a Person type with an age accessor; the comparator supplies ordering independently of the class.

### Exercise 12. Can the function return a `BonusScore` from List<BonusScore> even though it is only Comparable<Score>?

**Answer:** Yes, with the bound `T extends Comparable<? super T>`; Score is a supertype of BonusScore, so compareTo(Score) accepts BonusScore.

### Exercise 13. Why not treat Number as a common comparable type for all Integers and Doubles?

**Answer:** Number does not define compareTo and a List<Number> can hold mixed Number types. You need a comparator with an explicit policy or conversion to a suitable domain type.

### Exercise 14. Complexity?

**Answer:** For n≥1, the method performs one pass and n-1 comparisons. Time is O(n) if compareTo is O(1), and auxiliary memory is typically O(1).

### Exercise 15. What if the user wants max by multiple criteria?

**Answer:** Use a composed Comparator such as `Comparator.comparingInt(...).thenComparing(...)` to specify tie-breaking criteria, avoiding forcing an arbitrary natural ordering onto the class when multiple business orderings exist.

## 22. Project Implementation Checklist

1. Does the input have a natural ordering, or is a Comparator needed?
2. Does T already have the `Comparable<? super T>` bound?
3. Is the bound too narrow (Comparable<T>) or too loose (raw Comparable)?
4. Does the API only need Iterable, or does it need Collection/List?
5. Are null containers, null elements, and empty input handled?
6. Is tie-breaking defined to keep the first or last element when compareTo==0?
7. Is compareTo consistent, transitive, and stable for the data under consideration?
8. Does the comparator depend on mutable state or external services that could alter ordering?
9. Are incompatible comparable types being mixed?
10. Could Collections.max or Stream.max be used instead of custom code?
11. Have the Java examples been compiled with matching class/file names and their stdout verified?
12. Have the error cases been compiled separately to diagnose type inference/bounds accurately?

## 23. Conclusion

To write a type-safe max-selection function, start from the `Comparable` contract rather than casts or comparison operators that do not apply to T. The signature:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

captures two key relationships: **T can be compared to a T via Comparable of T or a suitable supertype**, and **the source can supply elements that are T or subtypes of T**. The body only needs a single pass, retaining the largest element seen and explicitly handling empty/null inputs.

For natural ordering, this is a classic exercise in bounded type parameters in Java Generics. For orderings that vary by business rule, use a Comparator-accepting variant. Do not weaken type safety with raw casts when the compiler reports incompatible bounds, and do not forget the behavioral contracts of compareTo.

**Remember:** A bound does more than let code call `compareTo`; it is a compile-time promise that comparison is meaningful for the element types the API accepts and returns.