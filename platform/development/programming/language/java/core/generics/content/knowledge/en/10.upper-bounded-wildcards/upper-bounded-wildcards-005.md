# Allowing `add(null)` Does Not Mean a Collection Must Accept `null`

In Java Generics, with a variable of type `Collection<? extends T>` (for example `List<? extends Number>`), the compiler does not allow adding an arbitrary concrete `T` object because the actual element type is unknown. However, **`add(null)` is still type-valid**. That only states that the expression `null` can be passed to a parameter having an unknown reference type; it **does not guarantee** that the referenced collection permits adding elements or accepts `null` at runtime.

These are two separate layers of rules to distinguish:

1. **Compile-time checking:** the generic type system determines whether an `add(...)` call is valid against `? extends T`.
2. **Collection contract and implementation at runtime:** the collection decides whether the add operation is supported and whether `null` values are accepted.

Understanding these two layers helps avoid confusing *generic type safety*, *mutability*, and *null policy*.

## 1. Why Does `add(null)` Compile With `? extends T`?

Consider the illustrative code inside a method:

```java
static void inspect(List<? extends Number> numbers) {
    Number first = numbers.isEmpty() ? null : numbers.get(0); // Valid.

    // numbers.add(10);   // COMPILE ERROR.
    // numbers.add(2.5);  // COMPILE ERROR.
    numbers.add(null);    // TYPE-VALID; runtime still depends on the list.
}
```

`List<? extends Number>` represents a list whose exact element type is unknown, yet is `Number` or a subtype of `Number`. That list could be:

- `List<Integer>`;
- `List<Double>`;
- `List<Number>`;
- or a list of another numeric type.

If `numbers.add(10)` were permitted, an `Integer` object could be inserted into an actual `List<Double>`. Therefore the compiler rejects it. Similarly, `2.5` is a `Double`, so it is unsafe for every element type that might stand behind `?`.

By contrast, **`null` is a special value convertible to any reference type in Java's standard type system**, including the unknown reference type created by the compiler when *capturing* a wildcard. It does not carry a concrete runtime type like `Integer` or `Double` that could corrupt the list's element type.

We can visualize the conditions as:

```text
List<? extends Number>
          |
          v
Actual element type: an unknown type X, X extends Number
          |
          +-- add(Integer): Not sure Integer is X -> compiler rejects
          +-- add(Double):  Not sure Double is X  -> compiler rejects
          +-- add(null):    null is compatible with X -> compiler accepts
```

The type validity of an `add(null)` call **does not grant permission to mutate the data structure** and **does not override a rule forbidding `null`** in a collection implementation.

## 2. Complete Example: Three Different Runtime Outcomes

Save the file `ExtendsNullDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Queue;

public class ExtendsNullDemo {
    static void attemptAddNull(String label, Collection<? extends Number> target) {
        try {
            boolean added = target.add(null); // Compiles.
            System.out.println(label + ": added=" + added);
        } catch (UnsupportedOperationException e) {
            System.out.println(label + ": UnsupportedOperationException");
        } catch (NullPointerException e) {
            System.out.println(label + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        ArrayList<Integer> mutable = new ArrayList<>(List.of(1, 2));
        attemptAddNull("ArrayList", mutable);
        System.out.println("contents=" + mutable);

        List<Integer> immutable = List.of(1, 2);
        attemptAddNull("List.of", immutable);

        Queue<Integer> queue = new ArrayDeque<>();
        attemptAddNull("ArrayDeque", queue);
    }
}
```

Run with Java 17 or later:

```bash
javac ExtendsNullDemo.java
java ExtendsNullDemo
```

Output:

```text
ArrayList: added=true
contents=[1, 2, null]
List.of: UnsupportedOperationException
ArrayDeque: NullPointerException
```

**Case-by-case analysis:**

- **`ArrayList<Integer>`:** is a list that supports adding elements and permits storing `null`. The `add(null)` call succeeds and returns `true`.
- **`List.of(1, 2)`:** returns an unmodifiable list. The `add(null)` call is rejected with `UnsupportedOperationException`. The `List.of(...)` factory methods themselves also reject `null` elements when creating a list.
- **`ArrayDeque<Integer>`:** supports adding non-null elements, yet actively forbids `null`. The `add(null)` call throws `NullPointerException` even when the queue is empty and capable of accepting more integers.

Common thread: all three calls use the parameter signature `Collection<? extends Number>` and **all pass the compiler**. The outcomes differ because the actual objects have different runtime contracts.

## 3. Two Independent Questions: Is It Modifiable, and Does It Accept `null`?

A collection may support modification yet forbid `null`; or it may contain `null` yet disallow adding elements via a particular operation. Therefore at least two independent properties must be considered:

| Collection and how it is created | Supports `add`? | Accepts `null`? | Typical outcome of `add(null)` |
| --- | --- | --- | --- |
| `new ArrayList<Integer>()` | Yes | Yes | Adding `null` succeeds |
| `new HashSet<Integer>()` | Yes | Yes | Succeeds the first time; if `null` is already present, `add` returns `false` |
| `new ArrayDeque<Integer>()` | Yes | No | `NullPointerException` |
| `new TreeSet<Integer>()` using natural ordering | Yes | No | `NullPointerException` |
| `List.of(1, 2)` | No | No | `UnsupportedOperationException` |
| `List.copyOf(source)` | No | No | `UnsupportedOperationException` |
| `Arrays.asList(1, 2)` | Does not support resizing | Can contain `null` | `UnsupportedOperationException` |
| `Collections.unmodifiableList(list)` | Not through the wrapper | Depends on backing list contents; wrapper cannot add | `UnsupportedOperationException` |

The table assumes calling `add(null)` on the standard implementations/instances listed in the first column. For custom collections or custom comparator configurations, the contract may differ. In particular, a `TreeSet` with a custom comparator must follow the rules of that comparator and implementation, so the "natural ordering" row should not be generalized to every `TreeSet`.

**Three distinct states must be separated:**

- **Can add elements:** `add` is an optional operation of `Collection`; several implementations intentionally do not support it.
- **Accepts `null`:** the collection can validly store `null` according to its contract.
- **Already contains `null`:** even a view that disallows adding elements may still expose `null` existing in the backing collection.

None of these three states can be concluded solely from the generic type `Collection<? extends T>`.

## 4. The `extends` Rule Protects Element Types, Not `null` Policy

Suppose:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> values = integers;

values.add(null);       // Compiles; ArrayList accepts null.
Number number = values.get(0); // Valid; number == null.
```

The following statements are all simultaneously true:

1. Variable `values` does not allow adding a concrete `Integer` value via `values.add(1)`, because the compiler does not know the actual element type behind the wildcard.
2. Expression `values.add(null)` is type-valid because `null` can be used in an argument position of an unknown reference type.
3. At runtime, `ArrayList` allows adding `null`; reading afterward may return `null`.
4. Java's standard type system does not treat a parameter `T extends Number` as a promise that values are always non-null.

Even a bound of `Number` or a custom interface is **not a non-null bound**. In standard Java 17, `T extends Number` describes nominal subtype relationships of non-null objects; it does not forbid `null` values.

Additional nullness-checking systems may apply annotations or separate rules to warn about or block `null`, but those are mechanisms outside the guarantees of standard wildcard syntax.

## 5. Not Only `add`: Passing `null` to `set` Also Passes Type Checking

With `List<? extends Number>`, `set(index, element)` requires an element of the unknown type just like `add`. Thus:

```java
List<Integer> base = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = base;

// view.set(0, 99); // COMPILE ERROR.
view.set(0, null);  // TYPE-VALID; ArrayList accepts null.
System.out.println(base); // [null, 20]
```

Type validity still does not say whether the list supports `set` or accepts `null`. An unmodifiable list may reject both `add` and `set`. A fixed-size list may **allow `set` while forbidding `add`**.

Standalone Java 17 example, saved as `FixedSizeNullDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class FixedSizeNullDemo {
    public static void main(String[] args) {
        List<Integer> fixedSize = Arrays.asList(1, 2);
        List<? extends Number> view = fixedSize;

        view.set(0, null);
        System.out.println("after set=" + fixedSize);

        try {
            view.add(null);
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }
    }
}
```

```bash
javac FixedSizeNullDemo.java
java FixedSizeNullDemo
```

Output:

```text
after set=[null, 2]
add=UnsupportedOperationException
```

`Arrays.asList` returns a list backed by a fixed-length array. It allows replacing existing element values via `set` and can hold `null`, yet does not allow growing in size via `add`. The example shows that "the collection accepts `null`" and "the `add` operation is supported" are genuinely two different things.

## 6. Distinguishing Two Exception Types When Adding `null`

Two very common exceptions:

### `UnsupportedOperationException`

This indicates that the collection **does not support the requested operation**. For example, `List.of(...)` returns an unmodifiable list. A call such as:

```java
List<? extends Number> readOnly = List.of(1, 2);
readOnly.add(null); // Compiles; runtime throws UnsupportedOperationException.
```

does not become valid for mutating state simply because the argument is `null`. The add operation itself is prohibited.

### `NullPointerException`

This can indicate that the implementation **forbids `null` values**. For example:

```java
Queue<? extends Number> numbers = new ArrayDeque<Integer>();
numbers.add(null); // Compiles; runtime throws NullPointerException.
```

`ArrayDeque` can add normal `Integer` elements through an appropriate reference such as `Queue<Integer>`, yet still rejects `null`. Thus `NullPointerException` here reflects data policy rather than generic invariance.

One cannot look only at `catch (NullPointerException)` to conclusively determine the cause in every program; the stack trace, API contract, and throw site determine the cause. In the example above, the cause is clearly known from `ArrayDeque`'s contract.

## 7. `List.of` and `List.copyOf` Check `null` Upon Creation

Another common mistake is thinking that simply assigning the result to `List<? extends Number>` will change the rules for accepting `null`. A wildcard is only a type property of the reference; it does not alter factory behavior.

Save as `NullFactoryDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class NullFactoryDemo {
    public static void main(String[] args) {
        try {
            List<Integer> first = List.of(1, null);
            System.out.println(first);
        } catch (NullPointerException e) {
            System.out.println("List.of rejected null");
        }

        try {
            List<Integer> second = List.copyOf(Arrays.asList(1, null));
            System.out.println(second);
        } catch (NullPointerException e) {
            System.out.println("List.copyOf rejected null");
        }

        List<? extends Number> safe = List.of(1, 2);
        System.out.println("size=" + safe.size());
    }
}
```

```bash
javac NullFactoryDemo.java
java NullFactoryDemo
```

Output:

```text
List.of rejected null
List.copyOf rejected null
size=2
```

- `List.of(1, null)` fails to create the list because the factory rejects `null`.
- `List.copyOf(...)` also inspects the source list and rejects it if it has a `null` element; it does not silently drop `null`.
- A valid list returned by `List.of` can be assigned to `List<? extends Number>` for reading numbers, yet calling `add(null)` through that reference still does not make it mutable.

The factory's null-rejection behavior and the resulting list's mutation-rejection behavior are two separate things, even though they can appear together.

## 8. `null` Can Be Read Out as `Number` Even When the Wildcard Bound Is `Number`

A frequent misconception: "`? extends Number` guarantees every `get` returns a valid `Number` object, so `doubleValue()` can be called right away." In reality, the compiler only guarantees that the result type is **compatible with `Number`**, not that the value is non-null.

Example:

```java
List<Integer> integers = new ArrayList<>();
integers.add(null);

List<? extends Number> source = integers;
Number first = source.get(0); // first == null.

// double x = first.doubleValue(); // Throws NullPointerException if executed.
```

If the data may contain `null`, it must be handled explicitly in the algorithm. For example, a summing method that skips `null` elements:

Save as `NullableNumberSum.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class NullableNumberSum {
    static double sumPresent(List<? extends Number> source) {
        double sum = 0.0;

        for (Number number : source) {
            if (number != null) {
                sum += number.doubleValue();
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
        source.add(null);

        System.out.println(sumPresent(source));
    }
}
```

```bash
javac NullableNumberSum.java
java NullableNumberSum
```

Output:

```text
6.0
```

This is a **business policy** of "skipping `null` elements", not a mandatory default. In another application, encountering `null` might be a data error that should throw an exception early, or should be represented by a clearer data model. What matters is not inferring a non-null guarantee from the `extends Number` bound.

## 9. `add(null)` With `?` and `? super T` Also Has Two Checking Layers

The `null` mechanism is not exclusive to `? extends`. With reference-type generic parameters, a variable typed with `?` or `? super T` also permits passing `null` in APIs that accept elements:

```java
static void examples(
        List<?> unknown,
        List<? extends Number> numbers,
        List<? super Integer> destination) {

    unknown.add(null);     // Type-valid.
    numbers.add(null);     // Type-valid.
    destination.add(null); // Type-valid.
    destination.add(10);   // Also valid: Integer satisfies the lower bound.

    // unknown.add(10); // Does not compile.
    // numbers.add(10); // Does not compile.
}
```

This snippet illustrates signatures and type checking, **not** a standalone runnable program. Whether any `add` call succeeds or throws an exception still depends on the actual list passed in.

Comparing semantics:

| Variable | Non-null value that can be added with `add` | Can `add(null)` be called from a type standpoint? |
| --- | --- | --- |
| `List<?>` | Cannot arbitrarily choose a concrete value | Yes |
| `List<? extends Number>` | Cannot arbitrarily choose a concrete `Number` | Yes |
| `List<? super Integer>` | `Integer` (and subtypes, if any) | Yes |
| `List<Integer>` | `Integer` | Yes |

The last column **only describes the compiler**, not a runtime guarantee. Do not turn this table into "the list is allowed to contain `null`"; each implementation has its own rules.

## 10. Difference Between `add(null)` and Casting a Typed Value to `null`

The compiler cares about the **static type of the expression** passed in, not only the runtime value. When a variable of a concrete type holds `null`, it still carries that variable's declared type:

```java
static void addExamples(List<? extends Number> target) {
    Integer boxed = null;

    target.add(null);   // Valid: null literal.
    // target.add(boxed); // Does not compile: boxed has type Integer.
    // target.add((Integer) null); // Does not compile: the expression has type Integer.
    // target.add((Number) null);  // Does not compile: the expression has type Number.
}
```

This is an especially easy point to miss: an argument whose runtime value is `null` is **not** automatically treated as a *null literal* during type analysis. `boxed` still has type `Integer`, and `Integer` is not proven compatible with the specific unknown capture type of `? extends Number`.

Similarly, in a call like `target.add(getNumberOrNull())`, the declared return type of the method may be `Number`. If so, the compiler still rejects the call even though at runtime the method might return `null`. Do not bypass checking with raw types or unchecked casts; redesign the API for its intended purpose.

## 11. Why Is `add(null)` Not a Workaround for Producer Limitations?

The practical rule PECS (*Producer Extends, Consumer Super*) reminds us that `? extends T` fits a source that **supplies** values of type `T` to the program. It does not claim that `? extends T` can never have any mutating calls; it states that **you cannot safely write an arbitrary concrete `T` object through that wildcard**.

Example:

```java
static double total(List<? extends Number> source) {
    double sum = 0.0;
    for (Number number : source) {
        if (number != null) {
            sum += number.doubleValue();
        }
    }
    return sum;
}
```

A read-only method like `total` has **no need to call `add(null)`** at all. Compile-time permission to add `null` is merely a consequence of type-conversion rules, not the design purpose of the `extends` wildcard.

If an API genuinely needs to add `Integer` values to a collection, use a parameter capable of accepting them:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Even `List<? super Integer>` does not guarantee runtime mutability. If the caller passes an unmodifiable `List<Number>`, the compiler still accepts the parameter type, yet `add(10)` can throw `UnsupportedOperationException`. Choosing the right wildcard solves **type safety**; actually being able to add also requires a mutable collection contract.

## 12. Common Mistakes

### Mistake 1: "The compiler allows `add(null)`, so the API guarantees `null` is accepted"

False, because type checking and data policy are two separate layers. `ArrayDeque` is an example that can add normal elements yet forbids `null`; `List.of` forbids all structural modifications.

**Right approach:** read the specific collection's contract; do not infer null policy from `? extends`.

### Mistake 2: "`? extends Number` always returns non-null values"

False. `Number n = list.get(0)` can easily yield `n == null` if the source contains `null`. Calling `n.doubleValue()` requires either a non-null guarantee from the data or an explicit check first.

**Right approach:** define the input contract and check for `null` when needed, independently of the wildcard.

### Mistake 3: "Not supporting `add` means `null` cannot exist in the collection"

False. `Arrays.asList(1, null)` contains `null` yet has a fixed size and does not support `add`. `Collections.unmodifiableList(backingList)` can also expose `null` elements from the backing list without allowing elements to be added through the wrapper.

**Right approach:** distinguish supported operations from permitted data states.

### Mistake 4: "Just cast an `Integer` to `Number` and add it through `extends`"

False. `target.add((Number) 10)` still does not compile with `List<? extends Number>`: the compiler cannot confirm that the actual type argument is `Number` rather than a subclass.

**Right approach:** use `List<? super Integer>` if writing `Integer` is needed, or an exact type `List<Integer>` when caller and callee agree.

### Mistake 5: "`(Integer) null` and the literal `null` are completely identical to the compiler"

False in the context of wildcard capture. The `null` literal converts to any reference type, whereas `(Integer) null` is an expression with static type `Integer`. Therefore, `target.add((Integer) null)` is still invalid for `List<? extends Number>`.

**Right approach:** pay attention to the static type of expressions; do not use casts or raw types to evade generic safety rules.

### Mistake 6: "`List.copyOf` automatically drops `null` elements"

False. `List.copyOf` rejects inputs containing `null` elements with a `NullPointerException`; if filtering is required, filter explicitly and decide data handling at the domain layer.

## 13. Designing APIs Without Relying on Accidental Permission for `add(null)`

If a method only uses a collection as a data source, write its contract for reading:

```java
static double average(List<? extends Number> values) {
    double sum = 0.0;
    int count = 0;

    for (Number number : values) {
        if (number != null) {
            sum += number.doubleValue();
            count++;
        }
    }
    return count == 0 ? 0.0 : sum / count;
}
```

If business requirements **forbid `null`**, validate explicitly at the API boundary instead of hoping wildcards or type bounds will do that job:

```java
import java.util.List;
import java.util.Objects;

static void requireNoNullElements(List<? extends Number> source) {
    for (Number value : source) {
        Objects.requireNonNull(value, "source must not contain null");
    }
}
```

The two examples above are illustrative methods: the second includes `import` statements for use inside an application's Java class. `Objects.requireNonNull` throws `NullPointerException` with the specified message if a `null` element is encountered; this method does not modify the collection and does not change how generics work.

If you need to build a new list containing only non-null values, create a concrete destination list and add each validated value. In that case, `null` acceptance and mutability belong to the design of the **destination object**, rather than being implicitly inferred from the source's `List<? extends Number>` type.

## 14. Self-Check Questions

**Question 1.** Given `List<? extends Number> xs`, which call passes the compiler?

```java
xs.add(null);        // A
// xs.add(1);         // B
// xs.add((Integer) null); // C
```

**Answer:** A. The `null` literal expression is compatible with the captured reference type; `Integer` is not proven compatible with every element type that might stand behind the wildcard.

**Question 2.** Why does `List.of(1, 2)` disallow `add(null)` even though the compiler accepts the call on `List<? extends Number>`?

**Answer:** `List.of` creates an unmodifiable list; `add` throws `UnsupportedOperationException` according to the collection contract.

**Question 3.** With `ArrayDeque<Integer>`, does `add(null)` fail because `Integer` is not a subtype of `Number`?

**Answer:** No. The reason is that `ArrayDeque` forbids `null`; the call already passed type checking.

**Question 4.** Can a `List<? extends Number>` containing `null` return `null` from `get(0)`?

**Answer:** Yes. The `Number` bound does not prove a value is non-null.

**Question 5.** `Arrays.asList(1, 2)` can execute `set(0, null)` yet cannot execute `add(null)`. Why?

**Answer:** A fixed-size list can replace an existing element's value with `null`, yet does not support operations that increase its size.

## 15. Key Takeaways

- With `List<? extends T>` where `T` is a reference type, `add(null)` **compiles**; `add(nonNullT)` is generally rejected because the actual element type is unknown.
- **Static type-level permission to call a method differs from runtime success of the operation.** `UnsupportedOperationException` reflects mutability; `NullPointerException` can reflect a policy forbidding `null`.
- `ArrayList` and `HashSet` can hold `null`; `ArrayDeque` does not accept `null`; `List.of` both forbids `null` on creation and forbids adding afterward.
- `set(index, null)` can also compile through `List<? extends T>`, yet success still depends on the collection and a valid index.
- The `extends Number` bound is **not** a promise of "no `null` elements." Reading algorithms must still handle `null` according to the data contract.
- API design should choose wildcards according to read/write direction, while separately specifying mutability and the data's `null` policy.

**Core conclusion:** `add(null)` is accepted at the *generic type-checking* step solely because `null` is compatible with an unknown reference type. A concrete collection may accept `null`, reject `null`, or reject all add operations; you must rely on the collection's actual contract to know what will happen.