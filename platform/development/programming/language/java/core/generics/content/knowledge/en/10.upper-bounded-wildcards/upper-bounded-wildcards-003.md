# Reading Elements Under an Upper Bound with the `? extends` Wildcard in Java Generics

## 1. Lesson Objective

In Java, `? extends UpperBound` is an **upper-bounded wildcard**. It expresses that the elements of a generic type may belong to **an unknown concrete type**, yet that concrete type is guaranteed to be `UpperBound` or a subtype of `UpperBound`.

Thanks to that guarantee, we can **read elements as `UpperBound`** without unchecked casts:

~~~java
List<Integer> integers = List.of(10, 20);
List<? extends Number> numbers = integers;

Number first = numbers.get(0); // Valid: Integer is a Number.
~~~

The result of `get(0)` could be an `Integer`, a `Double`, or another subtype of `Number`; the compiler only commits that it is **safely assignable to `Number`**. This is the core mechanism of this lesson. We will distinguish between "knowing the upper bound" and "knowing the exact element type", understand why reading is allowed while arbitrary adding is not, and apply that principle to write Java 17+ APIs.

## 2. Understanding `List<? extends Number>` Accurately

Consider a source that has a concrete element type but is viewed through a wildcard:

~~~java
List<Integer> integers = List.of(1, 2, 3);
List<? extends Number> source = integers;
Number first = source.get(0);
~~~

The compiler treats the element type of `source` as an **unknown** type (wildcard capture) with an upper bound of `Number`. Therefore `get(0)` can be read as `Number`, whereas it cannot be implicitly assigned to `Integer`: another call site might pass a `List<Double>`.

In this lesson on **reading under an upper bound**, the focus is not only on identifying which subtypes are accepted, but also on **which behaviors of `Number` can be safely called after retrieving an element**, iteration methods, null/heap pollution boundaries, and preserving subtypes with generic methods.

## 3. Under What Type Does the Compiler Allow Reading?

| Declared list type | Safe type when reading via `get(...)` | Notes |
| --- | --- | --- |
| `List<Integer>` | `Integer` | Concrete type argument is known. |
| `List<Number>` | `Number` | May contain multiple subtypes of `Number`. |
| `List<? extends Number>` | `Number` | Elements belong to an *unknown* subtype of `Number`. |
| `List<? extends Integer>` | `Integer` | Safe read type is `Integer`; `Integer` itself is final. |
| `List<? extends CharSequence>` | `CharSequence` | Methods of `CharSequence`, such as `length()`, can be called. |
| `List<?>` | `Object` | Unbounded wildcard corresponds to an upper bound of `Object`. |

Code illustrating valid reads:

~~~java
List<? extends Number> numbers = List.of(3, 5);
Number number = numbers.get(0);
double value = numbers.get(1).doubleValue(); // Method of Number.

List<? extends CharSequence> names = List.of("Java", "Generics");
CharSequence name = names.get(0);
int length = names.get(1).length();

List<?> unknown = List.of("A", "B");
Object element = unknown.get(0);
~~~

However, you cannot arbitrarily assign a result from a broad bound to a concrete subtype:

~~~java
List<? extends Number> numbers = List.of(3, 5);

// DOES NOT compile: Number cannot be guaranteed to be Integer.
Integer integer = numbers.get(0);

// DOES NOT compile: reading from List<?> is only guaranteed to be Object.
String string = List.of("A").stream().findFirst().orElse("");
// On its own the line above is valid because of Stream<String>, NOT an example of List<?>.
~~~

In the second situation, the exact invalid example to examine is:

~~~java
List<?> unknown = List.of("A", "B");
String value = unknown.get(0); // DOES NOT compile: requires Object or a type check.
~~~

You should not write `(Integer) numbers.get(0)` merely because you saw the original list created from `Integer` somewhere. If the API only promises `Number`, design callers to depend on `Number`, or use a type parameter structure to preserve `Integer` information when truly needed.

## 4. Safe Read Operations on `? extends`

### 4.1. Calling Methods of the Upper Bound

~~~java
static double sum(List<? extends Number> numbers) {
    double result = 0.0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
~~~

The snippet above is an **illustrative method that needs to be placed inside a Java class with `import java.util.List`**. It accepts many concrete lists:

~~~java
sum(List.of(1, 2, 3));   // List<Integer> -> 6.0
sum(List.of(1.5, 2.5)); // List<Double>  -> 4.0
~~~

We use `doubleValue()` because `Number` declares that method. This is a numeric value conversion that can lose precision for types like `BigDecimal`; in monetary applications, use concrete domain types and exact arithmetic rather than assuming a `double` sum is always appropriate.

### 4.2. `get`, for-each, Iterator, and Stream All Respect the Upper Bound

~~~java
List<? extends Number> numbers = List.of(1, 2, 3);

Number a = numbers.get(0);
for (Number n : numbers) {
    System.out.println(n.intValue());
}
java.util.Iterator<? extends Number> it = numbers.iterator();
Number b = it.next();

double total = numbers.stream()
        .mapToDouble(Number::doubleValue)
        .sum();
~~~

Each access pattern relies on **the same guarantee**: the retrieved element is a subtype of `Number`. `mapToDouble(Number::doubleValue)` works because each element can be viewed as a `Number`.

Manual `(Number)` casts are unnecessary. The compiler has already checked static compatibility for every operation within the valid generic type bounds.

### 4.3. Using an Interface as the Upper Bound

Not only classes like `Number`, an upper bound can also be an interface:

~~~java
static void printLengths(List<? extends CharSequence> values) {
    for (CharSequence text : values) {
        System.out.println(text.length());
    }
}
~~~

The method accepts `List<String>` or lists of other types implementing `CharSequence` (such as `StringBuilder`), and uses only the API guaranteed by `CharSequence`.

## 5. Why Is Reading Allowed While Arbitrary Element Addition Is Not?

The signature `List<? extends Number>` **allows retrieving values under the upper bound**, yet does not expose an exact element type for inserting a new `Integer` or `Double`:

~~~java
List<Double> actual = new ArrayList<>(List.of(1.5));
List<? extends Number> numbers = actual;
Number first = numbers.get(0);
// numbers.add(5); // Compile error: the unknown type may not accept Integer.
~~~

Reading out a `Number` is valid because every subtype of `Number` can be used as `Number`. The reverse is not true: an `Integer` is not guaranteed to belong to *every* possible unknown subtype.

The `add(null)` exception is only permitted at the **type-checking layer**, and does not guarantee that the collection supports mutation or nulls. `clear()` can also compile. For proofs of the no-adding-`T` rule, capture helpers, and strategies for switching to `? super T`, refer to the next dedicated lesson; this lesson focuses on **safe reading and the limits on using read values**.

## 6. Complete Java 17+ Example: Reading From Multiple Number Types

Create the file **ReadUpperBoundDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReadUpperBoundDemo {
    static double total(List<? extends Number> numbers) {
        double sum = 0;
        for (Number number : numbers) {
            sum += number.doubleValue();
        }
        return sum;
    }

    static <T extends Number> T firstTyped(List<? extends T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4, 6));
        List<Double> doubles = List.of(1.5, 2.5);

        List<? extends Number> view = integers;
        Number first = view.get(0);
        System.out.println("first: " + first);
        System.out.println("int total: " + total(integers));
        System.out.println("double total: " + total(doubles));

        Integer typed = firstTyped(integers);
        System.out.println("typed first: " + typed);

        List<? extends Integer> narrow = integers;
        Integer exact = narrow.get(1);
        System.out.println("narrow: " + exact);

        List<? extends Number> mutableView = integers;
        mutableView.remove(1);
        System.out.println("after remove: " + integers);

        List<? extends Number> nullable = new ArrayList<Integer>();
        nullable.add(null);
        System.out.println("null entry: " + nullable.get(0));

        List<?> unknown = List.of("hello");
        Object value = unknown.get(0);
        System.out.println("unknown: " + value);
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac --release 17 -Xlint:all ReadUpperBoundDemo.java
java ReadUpperBoundDemo
~~~

**Exact stdout** (sample compiled with `javac --release 17 -Xlint:all`, producing no unchecked warnings):

~~~text
first: 2
int total: 12.0
double total: 4.0
typed first: 2
narrow: 4
after remove: [2, 6]
null entry: null
unknown: hello
~~~

Part-by-part explanation:

1. `List<Integer>` is assignable to `List<? extends Number>`; the value from `get(0)` is safely read as `Number`.
2. `total` accepts both `List<Integer>` and `List<Double>`, using only methods of `Number`.
3. `firstTyped` preserves the type relationship `T` in the return value, so `Integer typed = firstTyped(integers)` requires no cast.
4. `List<? extends Integer>` allows reading as `Integer` because that is a tighter upper bound.
5. `remove(1)` mutates the **original list** through a wildcard reference; the upper bound does not make a list immutable.
6. `add(null)` is accepted by the compiler for a mutable `ArrayList`, though API callers must handle the case where a read element is `null`.
7. `List<?>` allows minimal reading as `Object`.

## 7. How to Preserve a Concrete Element Type When Needed?

If code only declares:

~~~java
List<? extends Number> view = List.of(1, 2, 3);
Number first = view.get(0);  // Guaranteed Number.
~~~

Then the fact that the runtime value happens to be `Integer` **does not upgrade `view`'s contract to `List<Integer>`**. The following line is a compile error:

~~~java
Integer exact = view.get(0); // NOT valid without a cast.
~~~

If your API genuinely needs to preserve the relationship between the input type and the return type, declare a **named type parameter**:

~~~java
static <T extends Number> T firstTyped(List<? extends T> values) {
    return values.get(0);
}

List<Integer> ints = List.of(10, 20);
Integer firstInteger = firstTyped(ints); // T is inferred to match Integer.
~~~

When calling `firstTyped` with a variable that has already been widened to `List<? extends Number>`, the compiler is still not allowed to promise a concrete `Integer`. A type parameter only retains **type relationships that the input itself can still express**; it does not recover evidence that has already been lost.

If you truly need to handle a specific subtype separately, you can use an explicit runtime check:

~~~java
Number item = view.get(0);
if (item instanceof Integer integer) {
    System.out.println(integer + 1);
}
~~~

This is a branch handling the runtime type of **a single element**. It does not prove that the *entire* list has type `List<Integer>`, because the code might be using a collection containing heterogeneous elements or one affected by raw/unchecked APIs.

## 8. When the Upper Bound Is `Object` and Comparison with `? super`

`List<?>` is shorthand for `List<? extends Object>` with respect to unbounded wildcard semantics. Consequently, `get` on `List<?>` is typed as `Object`:

~~~java
List<?> anything = List.of("A", 1, 2.5);
Object first = anything.get(0);
~~~

When an API only wants to print every element or check `equals`/`toString`, `List<?>` may be the clearest choice. There is no reason to constrain to `Number` if the algorithm uses no features of `Number`.

Meanwhile, with a **lower-bounded wildcard**:

~~~java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(42);             // Valid.
Object value = sink.get(0); // Only Object is guaranteed.
~~~

`? super Integer` describes an unknown **supertype container for `Integer`** (possibly `Integer`, `Number`, or `Object`). Reading from it only guarantees `Object`. Quick comparison table:

| View type | Safely read as | Add `Integer` |
| --- | --- | --- |
| `List<Integer>` | `Integer` | Yes, if the list supports modification. |
| `List<Number>` | `Number` | Yes, if the list supports modification. |
| `List<? extends Number>` | `Number` | No, because the concrete subtype is unknown. |
| `List<? super Integer>` | `Object` | Yes, if the list supports modification. |
| `List<?>` | `Object` | No, except `null`. |

PECS is a guideline for choosing **API parameters**: an input primarily supplying values to read → `extends`; an input primarily receiving values to write → `super`. PECS should not be misunderstood as a rule forbidding reading from `super` or forbidding all mutating operations on `extends`.

## 9. When Can Reading Elements Fail?

### 9.1. Empty List or Invalid Index

`List<? extends Number> numbers = List.of();` is completely valid. However, `numbers.get(0)` throws `IndexOutOfBoundsException`. A wildcard does not guarantee that a collection has elements.

Use for-each iteration, check `isEmpty()`, or validate indices properly if reading at a fixed position.

### 9.2. `null` Values

A collection that permits `null` may contain `null` even when typed as `List<? extends Number>`:

~~~java
List<? extends Number> numbers = new ArrayList<Integer>();
numbers.add(null);
Number n = numbers.get(0); // n == null
// n.doubleValue();          // Throws NullPointerException if uncommented.
~~~

**Type** safety does not imply **non-null**. Only call methods on the value after understanding the API's nullability contract.

### 9.3. Heap Pollution From Raw/Unchecked Code

A program can break the static guarantees of generics using raw types or unchecked conversions:

~~~java
List raw = new ArrayList<String>();
raw.add("not-a-number");               // Raw API: unchecked warning.
List<? extends Number> claimed = raw;  // Unchecked conversion.
Number n = claimed.get(0);             // May throw ClassCastException at runtime.
~~~

This is an **intentional counterexample**, not a pattern to put into production. When reading as `Number`, the compiler/JVM may have to perform a runtime type check due to type erasure. If the raw list actually contains a `String`, that check will fail. This does not mean `? extends Number` is unsafe: the fault came from bypassing generic checks earlier with raw/unchecked code.

### 9.4. An Upper Bound Does Not Guarantee Every Subtype Method

~~~java
List<? extends Number> values = List.of(1, 2);
Number a = values.get(0);

// DOES NOT compile because Number does not have a compareTo(Integer) method.
int result = values.get(0).compareTo(2);
~~~

`Integer` has its own methods, yet the common type `Number` does not promise all of them. Rely only on the API of the upper bound, or use a tighter generic type when the algorithm requires additional capabilities.

## 10. Designing Data-Accepting Methods: Which Signature Should You Use?

| Need | Suitable signature | Reason |
| --- | --- | --- |
| Sum numbers, read-only | `double total(List<? extends Number> input)` | Accepts many different numeric lists; only needs methods from `Number`. |
| Retrieve one number and preserve the subtype at the call site | `<T extends Number> T first(List<? extends T> input)` | Binds the result to the caller's `T`. |
| Iterate over any values regardless of type | `void print(List<?> input)` | `Object` is sufficient. |
| Write `Integer` values into a collection | `void fill(List<? super Integer> target)` | Can insert `Integer`; no need to read as `Number`. |
| Must append both `Integer` and `Double` into the same list | `void appendBoth(List<Number> target)` (or an appropriate target API) | Needs a contract accepting `Number` values; cannot arbitrarily write through `? extends`. |

If you have a `List<Integer>` and need to create a **new list** allowing insertion of multiple `Number` subtypes, create a copy:

~~~java
List<Integer> ints = List.of(1, 2);
List<Number> mixed = new ArrayList<>(ints);
mixed.add(2.5);
~~~

This is a **safe copy constructor**, not a cast or a change in subtyping rules. The source `List<Integer>` remains its own separate list.

## 11. Common Misconceptions and Self-Check

| Misconception | Correct explanation |
| --- | --- |
| "`? extends Number` only holds `Number`, and does not accept `Integer`." | It is designed to accept both `Number` and subtypes such as `Integer` and `Double`. |
| "Once `List<Integer>` is assigned to `List<? extends Number>`, `get` returns `Integer` via the view variable." | The view variable only guarantees that the read result can be used as `Number`. |
| "Any `Number` can be added because the bound is `Number`." | No: the compiler does not know the wildcard's concrete subtype. |
| "`? extends` creates a read-only/immutable list." | No: `remove`/`clear` are still possible if the implementation supports them; `add(null)` is also type-valid. |
| "If you can read `Number`, there is definitely no `null`." | Elements can be `null` if the collection permits it. |
| "You need to cast `(Number) numbers.get(i)` to be safe." | Manual casting is unnecessary; the type system already guarantees the upper bound in type-safe generic code. |
| "`List<?>` and `List<? extends Number>` read with the same type." | `List<?>` only guarantees `Object`; `List<? extends Number>` guarantees `Number`. |

**Review questions**

1. Why can `List<Double>` be passed to `total(List<? extends Number>)`? **Because `Double <: Number` and the wildcard allows a type argument that is a subtype of `Number`.**
2. Why is `Number n = values.get(0)` valid when `values` has type `List<? extends Number>`? **Because the captured type of the element is guaranteed to be a subtype of `Number`.**
3. Why is `values.add(10)` disallowed? **Because the concrete element type could be `Double` or another subtype that does not accept `Integer`.**
4. Is `List<? extends Number>` an immutable list? **No.** The wildcard only restricts write operations that would lose type safety.
5. When using `List<?>`, what is the safe type to receive `get(0)`? **`Object`.**
6. If you want `get` to preserve the `Integer` type when the caller passes `List<Integer>`, what should you do? **Use a signature with a type parameter `<T extends Number> T firstTyped(List<? extends T>)` or use `List<Integer>` directly when the API is specialized.**

## 12. Authoritative References

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): semantics of upper-bounded wildcards and containment.
- [JLS Java SE 17 §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): subtyping relationships with parameterized types.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): how the compiler handles unknown types represented by wildcards.
- [Oracle Java Tutorials — Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html): pattern for using `extends` wildcards to process lists of subtypes of a common type.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `get`, `add`, `remove`, `clear`, and exceptions when accessing/modifying lists.