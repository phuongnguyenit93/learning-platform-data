# anyMatch(), allMatch(), and noneMatch() in Java Stream

## 1. Three Terminal Operations for Answering Yes/No Questions

In `java.util.stream.Stream`, the three methods `anyMatch()`, `allMatch()`, and `noneMatch()` test a condition (*predicate*) on the elements of a stream and return a primitive **`boolean`** result. They are **terminal operations**: calling them triggers consumption of the pipeline; the result is not a new stream.

The three questions:

- **`anyMatch(predicate)`**: Is there **at least one** element that satisfies the condition?
- **`allMatch(predicate)`**: Do **all** elements satisfy the condition?
- **`noneMatch(predicate)`**: Do **no elements** satisfy the condition?

Example with `List.of(2, 4, 7)`:

~~~java
List<Integer> values = List.of(2, 4, 7);

boolean hasOdd = values.stream().anyMatch(n -> n % 2 != 0);  // true
boolean allEven = values.stream().allMatch(n -> n % 2 == 0); // false
boolean noNegative = values.stream().noneMatch(n -> n < 0); // true
~~~

The statements above are **illustrative snippets**; they require importing `java.util.List` and being placed inside a method. Each call to `values.stream()` creates **a new stream**. A stream cannot be reused after a terminal operation.

Unlike `filter()`, these three methods **do not collect or retain elements**; they directly answer a true/false question. `filter()` is an intermediate operation and returns `Stream<T>`, whereas `anyMatch`/`allMatch`/`noneMatch` return `boolean`.

**Quick selection guide:** If the problem is phrased as “there is at least one”, use `anyMatch`; “every” / “all”, use `allMatch`; “there is not any” / “none”, use `noneMatch`.

## 2. API Signatures and the Role of Predicate

Signatures on `Stream<T>`:

~~~java
boolean anyMatch(Predicate<? super T> predicate);
boolean allMatch(Predicate<? super T> predicate);
boolean noneMatch(Predicate<? super T> predicate);
~~~

These are abbreviated signatures from the Java SE API, **not code redeclaring the `Stream` interface**.

`Predicate<T>` is a functional interface in `java.util.function` with a single abstract method:

~~~java
boolean test(T value);
~~~

Therefore, the expression `n -> n > 10` is assigned to `Predicate<Integer>` when the source is `Stream<Integer>`, or to `IntPredicate` if the source is `IntStream`. A `Predicate` must return **`boolean`** or a result compatible with `boolean`; Java does not treat a non-zero number as `true`.

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();

boolean hasNonBlank = List.of("", "  ", "Java")
        .stream()
        .anyMatch(nonBlank);             // true
~~~

This snippet requires importing `java.util.List` and `java.util.function.Predicate`. `String.isBlank()` has been available since Java 11; the example is suitable for Java 17+.

Variants for primitive streams accept specialized predicates to avoid boxing each element:

| Stream source | Callback type | SAM |
|---|---|---|
| `Stream<T>` | `Predicate<? super T>` | `boolean test(T)` |
| `IntStream` | `IntPredicate` | `boolean test(int)` |
| `LongStream` | `LongPredicate` | `boolean test(long)` |
| `DoubleStream` | `DoublePredicate` | `boolean test(double)` |

For example, `IntStream.rangeClosed(1, 5).allMatch(n -> n > 0)` returns `true`. All three matching operations exist on the corresponding primitive streams.

## 3. Important Truth Table — Including Empty Streams

Suppose predicate `P(x)` returns `true` for an element that meets the condition.

| Source state | `anyMatch(P)` | `allMatch(P)` | `noneMatch(P)` |
|---|---:|---:|---:|
| Has at least one element and **all pass** | `true` | `true` | `false` |
| Has passing elements and failing elements | `true` | `false` | `false` |
| Has at least one element and **none pass** | `false` | `false` | `true` |
| **No elements** (empty stream) | `false` | `true` | `true` |

The last row is very important:

~~~java
Stream.<Integer>empty().anyMatch(n -> n > 0)  // false
Stream.<Integer>empty().allMatch(n -> n > 0)  // true
Stream.<Integer>empty().noneMatch(n -> n > 0) // true
~~~

**Why does `allMatch` on an empty source return `true`?** The statement “every element satisfies the condition” is false only if **a counterexample** can be found. In an empty source there is no violating element, so in mathematical logic the statement is true; this phenomenon is called **vacuous truth**. `noneMatch` is also true because no matching element is found. Conversely, `anyMatch` needs **an existential witness**, and an empty source has no witness.

Do not conclude that `allMatch` returning `true` means “the data has at least one element and all of them pass”. If business logic **requires data to be present**, you must check the non-empty condition **separately** or use a different validation structure.

### 3.1. Business Example: Is an Empty List Considered Valid?

Suppose you need to verify “all items in the order have a positive quantity”, while the business requirement also states “the order must have at least one item”. Writing only:

~~~java
boolean valid = lines.stream().allMatch(line -> line.quantity() > 0);
~~~

is **not sufficient** because if `lines` is empty, `valid` is still `true`. Given an existing `lines` of type `List<Line>`, a more appropriate check is:

~~~java
boolean valid = !lines.isEmpty()
        && lines.stream().allMatch(line -> line.quantity() > 0);
~~~

The `!lines.isEmpty()` part confirms the existence condition; the `allMatch` part confirms the validity of all items. The `&&` operator short-circuits, so when the list is empty, there is no need to create and traverse the stream afterward.

## 4. Short-Circuiting Mechanism

All three matching methods are **short-circuiting terminal operations**: they can reach a conclusion before traversing all elements, depending on what has been seen.

- `anyMatch(P)` can return **`true` as soon as it finds one matching element**. If no element matches in a finite source, it must inspect everything to conclude `false`.
- `allMatch(P)` can return **`false` as soon as it finds one non-matching element**. If every element in a finite source matches, it must inspect everything to return `true`.
- `noneMatch(P)` can return **`false` as soon as it finds one matching element**. If no element matches in a finite source, it must inspect everything to return `true`.

Conceptual diagram:

~~~text
anyMatch(P):    encounters P(x) == true  ──► concludes true
allMatch(P):    encounters P(x) == false ──► concludes false
noneMatch(P):   encounters P(x) == true  ──► concludes false
~~~

This **does not mean Java will always call the predicate exactly N times** in every configuration: evaluation order, parallel state, pipeline optimizations, and intermediate operations can affect the actual number of calls. In particular, **a parallel stream may check multiple elements concurrently**, so side effects must never rely on the order or number of checks.

### 4.1. Complete Program: Counting Calls in a Deterministic Sequence

Save the file as **`MatchShortCircuitDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

public class MatchShortCircuitDemo {
    static Predicate<Integer> traced(
            String label,
            AtomicInteger checks,
            Predicate<Integer> rule) {
        return value -> {
            checks.incrementAndGet();
            System.out.println(label + ":" + value);
            return rule.test(value);
        };
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        AtomicInteger anyChecks = new AtomicInteger();
        boolean any = numbers.stream().anyMatch(
                traced("any", anyChecks, n -> n == 2));

        AtomicInteger allChecks = new AtomicInteger();
        boolean all = numbers.stream().allMatch(
                traced("all", allChecks, n -> n < 3));

        AtomicInteger noneChecks = new AtomicInteger();
        boolean none = numbers.stream().noneMatch(
                traced("none", noneChecks, n -> n == 3));

        System.out.println("any=" + any + ",checks=" + anyChecks.get());
        System.out.println("all=" + all + ",checks=" + allChecks.get());
        System.out.println("none=" + none + ",checks=" + noneChecks.get());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac MatchShortCircuitDemo.java
java MatchShortCircuitDemo
~~~

Stdout of the **sequential pipeline on `List.of(1,2,3,4)`**:

~~~text
any:1
any:2
all:1
all:2
all:3
none:1
none:2
none:3
any=true,checks=2
all=false,checks=3
none=false,checks=3
~~~

Explanation:

1. `anyMatch(n -> n == 2)` checks `1` then `2`; it finds a matching result and stops, so it does not need to check `3` or `4`.
2. `allMatch(n -> n < 3)` checks `1`, `2`, and then encounters `3` which fails the condition, concluding `false`.
3. `noneMatch(n -> n == 3)` encounters `3` which satisfies the predicate, so the proposition “none match” is false, concluding `false`.
4. `AtomicInteger` is only used to illustrate the call count; it is not needed for a pure predicate. Printing inside the predicate is an **intentional side effect for learning the mechanism**, not a pattern suitable for every pipeline.

In this program we use **three separate streams**, created with `numbers.stream()` for each matching operation. A stream already consumed by a terminal operation must not be reused.

## 5. Java 17 Program: Data Classification and Empty Sources

Save as **`MatchBusinessDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class MatchBusinessDemo {
    record Item(String name, int quantity, boolean approved) {}

    static boolean canSubmit(List<Item> items) {
        return !items.isEmpty()
                && items.stream().allMatch(item ->
                        item.quantity() > 0 && item.approved());
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("Pen", 2, true),
                new Item("Book", 1, true),
                new Item("Bag", 0, false)
        );

        boolean anyUnavailable = items.stream()
                .anyMatch(item -> item.quantity() == 0);
        boolean allApproved = items.stream()
                .allMatch(Item::approved);
        boolean noneNegative = items.stream()
                .noneMatch(item -> item.quantity() < 0);

        System.out.println("unavailable=" + anyUnavailable);
        System.out.println("allApproved=" + allApproved);
        System.out.println("noneNegative=" + noneNegative);
        System.out.println("canSubmit=" + canSubmit(items));

        List<Item> empty = List.of();
        System.out.println("emptyAny=" +
                empty.stream().anyMatch(Item::approved));
        System.out.println("emptyAll=" +
                empty.stream().allMatch(Item::approved));
        System.out.println("emptyNone=" +
                empty.stream().noneMatch(Item::approved));
        System.out.println("emptyCanSubmit=" + canSubmit(empty));

        boolean someMultipleOfFour = IntStream.rangeClosed(1, 10)
                .anyMatch(n -> n % 4 == 0);
        System.out.println("primitive=" + someMultipleOfFour);
    }
}
~~~

Compile and run:

~~~bash
javac MatchBusinessDemo.java
java MatchBusinessDemo
~~~

Exact stdout:

~~~text
unavailable=true
allApproved=false
noneNegative=true
canSubmit=false
emptyAny=false
emptyAll=true
emptyNone=true
emptyCanSubmit=false
primitive=true
~~~

**Reading each check:**

- `anyUnavailable` is `true` because `Bag` has `quantity() == 0`.
- `allApproved` is `false` because `Bag.approved()` is `false`.
- `noneNegative` is `true` because no item has a negative quantity. **No negative numbers** does not mean **all positive numbers**: the number `0` still exists.
- `canSubmit` requires both at least one item and every item having `quantity() > 0 && approved`; because `Bag` is invalid, the result is `false`.
- For an empty list, `anyMatch`/`allMatch`/`noneMatch` are `false`, `true`, `true` respectively; `canSubmit(empty)` remains `false` thanks to the `!items.isEmpty()` check.
- `IntStream.rangeClosed(1,10)` produces primitive integers; the predicate receives `int` via `IntPredicate`. There are numbers divisible by 4 (such as `4`), so `primitive` is `true`.

Real-world applications should clarify business rules: “no defective items” may be true for an empty set, whereas “an order eligible for submission” usually requires at least one item. The difference comes from business requirements, not a bug in Java Stream.

## 6. The Mathematics Behind the Three Methods

The three matching operations can be understood through quantifiers in logic:

~~~text
anyMatch(P)   ⇔  ∃x in stream: P(x)
allMatch(P)   ⇔  ∀x in stream: P(x)
noneMatch(P)  ⇔  there does not exist x: P(x)
~~~

Where `∃` means “there exists” and `∀` means “for all”.

For the same finite sequence of data and a **pure, deterministic** predicate (not depending on state, time, or side effects), we have the following logical relationships:

~~~java
noneMatch(P)  == !anyMatch(P)
allMatch(P)   == !anyMatch(P.negate())
noneMatch(P)  == allMatch(P.negate())
anyMatch(P)   == !noneMatch(P)
~~~

These are **relationships between boolean results**, not code calling `P` variables directly. When applying them in Java, a **new stream** must be created for each terminal operation execution. For example:

~~~java
Predicate<Integer> positive = n -> n > 0;

boolean a = numbers.stream().noneMatch(positive);
boolean b = !numbers.stream().anyMatch(positive);

// With the same stable source contents, a and b are equal.
~~~

This is an illustrative snippet; it requires `numbers` as a collection of numbers and importing `java.util.function.Predicate`.

**Do not treat the formulas above as equivalent with respect to side effects.** Two ways of checking may invoke the predicate a different number of times or in a different order when using different sources, parallel streams, or predicates that read time or mutable variables; they may even throw exceptions at different times. They are equivalent in **logical meaning on the same set of elements and a stable predicate**.

### 6.1. Distinguishing `allMatch(P)` and `noneMatch(P)`

Do not assume `noneMatch(P)` is `allMatch(P)` just because both can return true. With source `[2,4]` and `P(n) = (n % 2 == 0)`:

- `allMatch(P)` returns `true` because all elements are even.
- `noneMatch(P)` returns `false` because there **are** actually even elements.
- `noneMatch(n -> n % 2 != 0)` returns `true` because there are no odd numbers.

If the requirement is “no record is locked” (all records are unlocked), you can write `allMatch(record -> !record.locked())` or `noneMatch(Record::locked)`. Choose the one whose naming is clearest for the business domain and avoids nesting too many negations.

### 6.2. Do Not Use `anyMatch(P)` as the Negation of `allMatch(P)`

`!allMatch(P)` means **there exists at least one element that does not satisfy `P`**, not “there exists no element that satisfies `P`”. For example, with data `[1,2]` and `P(n) = (n > 1)`: `allMatch(P)` is false and `anyMatch(P)` is true at the same time. You must use `anyMatch(P.negate())` to express the negation of `allMatch(P)`.

## 7. When to Use `match` Instead of `filter`, `count`, or `findAny`?

Compare two ways of asking “is there at least one element greater than 100?”:

~~~java
boolean exists = values.stream().anyMatch(n -> n > 100);
~~~

and:

~~~java
boolean exists = values.stream()
        .filter(n -> n > 100)
        .count() > 0;
~~~

Both forms can produce the same result on a finite collection with a pure predicate, but **`anyMatch` expresses the existence intent directly** and supports short-circuiting as soon as a matching element is seen. `filter(...).count()` is expressed as a **counting** problem, which may have to inspect the entire source as required by counting, although optimizations permitted by the Stream API may alter how it executes.

### 7.1. When Is `findAny` Better?

`findAny()` returns `Optional<T>`, which is useful when you need **the found element itself**, not just a boolean flag:

~~~java
Optional<Integer> found = values.stream()
        .filter(n -> n > 100)
        .findAny();
~~~

If you only need a true/false answer, `anyMatch` is usually clearer. If you need the first record in encounter order, consider `findFirst()` on an ordered source; `anyMatch` does not return any element and does not promise to tell you which element made the condition true.

### 7.2. `noneMatch` Instead of `filter(...).findAny().isEmpty()`

~~~java
boolean noInvalid = records.stream()
        .noneMatch(record -> !record.isValid());
~~~

This snippet clearly states the requirement “there are no invalid records”. You can use `allMatch(Record::isValid)` to reduce double negation if the `isValid()` method has a positive meaning and is easy to read.

### 7.3. When You Truly Need a Count, Just Use `count`

If the business logic asks “how many records have errors”, `filter(...).count()` is what expresses the problem accurately. `anyMatch` only yields a `boolean` and cannot replace a count that needs to know the quantity.

## 8. Combining with map, filter, and flatMap

Matching operations usually sit at the end of a pipeline.

### 8.1. Checking Data After Transformation

~~~java
boolean hasBlank = names.stream()
        .map(String::strip)
        .anyMatch(String::isEmpty);
~~~

If `names` is a `List<String>` containing no nulls, the pipeline checks whether any string consists only of whitespace or is empty after `strip()`. With input that may contain null, `String::strip` can throw `NullPointerException`; a separate null policy is needed.

### 8.2. Checking Elements in Nested Groups

~~~java
boolean hasNegative = groups.stream()
        .flatMap(List::stream)
        .anyMatch(n -> n < 0);
~~~

With `groups` of type `List<List<Integer>>` containing no null groups, `flatMap(List::stream)` turns the groups into a flat stream, and `anyMatch` determines whether there is **any negative number** across all groups.

If the goal is “every group has at least one negative number”, the meaning is different:

~~~java
boolean everyGroupHasNegative = groups.stream()
        .allMatch(group -> group.stream().anyMatch(n -> n < 0));
~~~

The second line checks **per group**, so for an empty group: `group.stream().anyMatch(...)` is false. When `groups` is empty, the outer `allMatch` is true by the vacuous truth rule; if the existence of at least one group is required, `!groups.isEmpty()` is needed.

Notice the difference between the two quantifiers:

~~~text
There is at least one negative number in any group:
    ∃ group, ∃ n ∈ group: n < 0

Every group has at least one negative number:
    ∀ group, ∃ n ∈ group: n < 0
~~~

Do not flatten too early if the requirement needs to check a condition **individually for each group**. `flatMap` loses group boundaries unless parent information is preserved.

### 8.3. Combining Named Predicates

Instead of a long conditional lambda:

~~~java
Predicate<String> goodName = name ->
        name != null && !name.isBlank() && name.length() <= 30;

boolean allGood = names.stream().allMatch(goodName);
~~~

You can extract the condition into a testable business method, or use `Predicate.and`/`or`/`negate` when clearer. A `Predicate` can be reused across multiple matching operations; however, avoid predicates with mutable state or side effects that make the result depend on the number of calls.

## 9. Infinite Streams and Short-Circuiting: Can Terminate, but Not Guaranteed

With an infinite `Stream.generate` or `Stream.iterate` source, matching **can** terminate if the decisive condition appears:

~~~java
boolean exists = java.util.stream.Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == 5);  // true, can stop when 5 is encountered.
~~~

However, a question without early decisive evidence may **never return**:

~~~java
// DO NOT RUN: an always-positive infinite source has no counterexample for allMatch to return false.
java.util.stream.Stream.generate(() -> 1)
        .allMatch(n -> n > 0);
~~~

Similarly, `noneMatch(n -> n < 0)` on an infinite source that always produces positive numbers cannot conclude true after a finite number of elements, because a negative element could still appear in the future. `anyMatch(n -> n < 0)` also cannot conclude false without knowing that the source has ended.

In practice, **set a finite bound** or use a source with a clear stopping point:

~~~java
boolean allPositive = java.util.stream.IntStream.rangeClosed(1, 10)
        .allMatch(n -> n > 0);
~~~

**Arithmetic warning:** `Stream.iterate(1, n -> n + 1)` uses boxed `Integer` and can overflow if run too far, though the example looking for `5` stops early. Do not use infinite sources to demonstrate correctness on large datasets without controlling the stopping point.

## 10. Parallel Streams and the Requirement for Side-Effect-Free Predicates

All matching operations support parallel streams, but they **do not guarantee sequential traversal or calling the predicate exactly once per element in every situation**. When one worker finds a decisive condition, other workers may already have started processing other elements.

Example:

~~~java
boolean anyError = records.parallelStream()
        .anyMatch(Record::hasError);
~~~

The snippet above illustrates using `records` as a collection of records with a `hasError()` method. The boolean result is the primary goal. If `hasError` is pure, thread-safe, and order-independent, the code is easier to reason about.

**Do not** place database writes, email sending, event publishing, or business counter increments inside a predicate and expect all elements to be visited:

~~~java
// Example NOT RECOMMENDED:
boolean found = records.parallelStream()
        .anyMatch(record -> {
            audit(record);   // side effect is not guaranteed to run for every record.
            return record.hasError();
        });
~~~

Because `anyMatch` can short-circuit, some records will not be audited. If the predicate is stateful and not thread-safe, parallel execution can also cause race conditions. Separate mandatory auditing steps from existence checks, or use another API for business control flow.

Even with sequential streams, inserting `peek` to count checks should only be used for debugging, not turned into a business contract.

## 11. Handling Nulls, Exceptions, and Invalid Data

### 11.1. Null Elements

`List.of(...)` does not allow null elements, but some other collections can contain null. If a predicate calls a method on a null element:

~~~java
boolean hasLong = nullableNames.stream()
        .anyMatch(name -> name.length() > 10);
~~~

this can throw `NullPointerException`. If you want to skip nulls:

~~~java
boolean hasLong = nullableNames.stream()
        .anyMatch(name -> name != null && name.length() > 10);
~~~

If you want to treat null as invalid:

~~~java
boolean allValid = nullableNames.stream()
        .allMatch(name -> name != null && !name.isBlank());
~~~

These snippets are illustrative examples with `nullableNames` as a `String` collection that may contain nulls. The `&&` condition short-circuits, so `length()`/`isBlank()` is not called when `name == null`.

### 11.2. Null Predicate

Passing `null` as the predicate argument is rejected by the API with a `NullPointerException`. Passing a lambda that produces a `Boolean` result equal to null and expecting Java to unbox it to `boolean` can also cause a runtime error if that unboxing is actually performed; write predicates with an explicit boolean result.

### 11.3. Checked Exceptions

`Predicate.test(T)` does not declare checked exceptions. If checking an element requires an I/O operation that may throw `IOException`, the lambda cannot let it escape as a checked exception without handling it. Solutions depending on business needs include handling it at an appropriate place, wrapping it in a controlled unchecked exception, or using a separate validation API with a clear error contract.

### 11.4. Exceptions Are Not `false` Results

If a predicate throws an exception, `anyMatch` does not automatically convert the exception to `false`, `allMatch` does not automatically convert it to `false`, and `noneMatch` does not automatically convert it to `true`. The exception propagates according to the pipeline/Java error-handling mechanism; do not assume these methods are “safe checks” regardless of internal logic.

### 11.5. Results May Change If Source Data Is Modified

Behavioral parameters of a Stream should be **non-interfering** and usually stateless. If a predicate modifies the source collection while traversing it, it can violate the Stream contract, leading to exceptions or unpredictable results. If the data source is modified concurrently without proper synchronization, a matching operation may no longer represent a consistent snapshot.

## 12. Common Mistakes When Choosing a Matching Operation

| Mistake | Why it is wrong / dangerous | How to fix |
|---|---|---|
| Thinking `allMatch` on an empty stream returns false | “All elements pass” is vacuously true | If at least one element is needed, check non-emptiness separately |
| Thinking `noneMatch(P) == allMatch(P)` | One means “none pass”, the other means “everyone passes” | Use `allMatch(P.negate())` with the same stable predicate |
| Using `!anyMatch(P)` to check “all elements pass” | `!anyMatch(P)` means none pass | Use `allMatch(P)` |
| Picking `anyMatch` when you want the found record itself | Returns boolean, not an element | Use `filter(...).findAny()`/`findFirst()` |
| Using `filter(...).count() > 0` just to check existence | Expresses intent less directly | Prefer `anyMatch` |
| Expecting the predicate to always run for all elements | Matching can short-circuit | Do not put mandatory side effects inside the predicate |
| Expecting `allMatch` to prove the collection has elements | Empty stream still returns true | Add a non-empty check if needed |
| Reusing the same stream for three matching operations | The stream is already consumed by the terminal operation | Create a new stream for each operation |
| Using matching on an infinite source without termination proof | May run forever | Bound the source / change the termination condition |
| Using an unsafe predicate in a parallel stream | Races and nondeterministic callback order | Use a stateless, thread-safe predicate |
| Relying on `null` being false in a condition | Can throw NPE | Define an explicit null policy |
| Using `allMatch` to sum or count | Only produces boolean | Use `sum`, `count`, `reduce`, or a collector |

Reading the method name and business requirement accurately usually prevents most mistakes: the three methods answer **three different kinds of propositions**, not just equivalent ways of writing a loop.

## 13. Practice Exercises with Answers

### 13.1. Checking Product Codes

Suppose `codes` is a non-null `List<String>`:

~~~java
boolean anyBlank = codes.stream().anyMatch(String::isBlank);
boolean allNonBlank = codes.stream().allMatch(code -> !code.isBlank());
boolean noneBlank = codes.stream().noneMatch(String::isBlank);
~~~

With the same stable data, `allNonBlank` and `noneBlank` have the same result. If `codes` is empty, **both are `true`**; if the business condition requires the list to contain codes, add `!codes.isEmpty()`.

### 13.2. Checking Condition Order

With `numbers = List.of(1, 2, 3)`:

~~~java
numbers.stream().anyMatch(n -> n > 2)    // true
numbers.stream().allMatch(n -> n > 2)    // false
numbers.stream().noneMatch(n -> n > 2)   // false
~~~

Replacing the predicate with `n -> n > 10` gives:

~~~java
anyMatch(n -> n > 10)  // false
allMatch(n -> n > 10)  // false
noneMatch(n -> n > 10) // true
~~~

The lines in this section are an **illustrative table of results for calls on a new source each time**, not a standalone Java file.

### 13.3. Every Group Is Valid

With `List<List<Integer>> groups`, requirement “every group has at least one positive number”:

~~~java
boolean valid = !groups.isEmpty()
        && groups.stream().allMatch(
                group -> !group.isEmpty()
                        && group.stream().anyMatch(n -> n > 0));
~~~

Checks for both the outer list and each group being non-empty were added, because the business rule **requires at least one group and each group to have at least one passing element**. Using only outer `allMatch` on empty data would yield a default true that may fail to reflect the existence requirement.

### 13.4. Can an Infinite Sequence Short-Circuit?

~~~java
boolean found = java.util.stream.Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == 3);
~~~

With sequential execution and stable logic, it can stop as soon as `3` is seen. However, the question “is there no `3` in this infinite sequence?” requires verifying a universal proposition; `noneMatch(n -> n == 3)` can also short-circuit at `3` to return **`false`**, rather than `true`. Do not confuse short-circuiting with automatically proving quantified propositions over infinity.

## 14. Checklist When Reviewing Java Stream Code

1. **Can the data source be empty?** If yes, clearly understand the corresponding `false/true/true` behavior.
2. **Does the problem need a boolean or the element/count itself?** If you need a record, use `findFirst`/`findAny`; if you need a count, use `count`.
3. **Does the business statement use “exists”, “every”, or “none”?** Choose `anyMatch`, `allMatch`, or `noneMatch` according to natural language.
4. **Is the predicate pure and non-interfering with the source?** Avoid mandatory side effects, especially in parallel streams.
5. **Can there be null data or exceptions?** Define a policy before using method references that might dereference null.
6. **Is the same stream being reused?** Each terminal operation requires a new stream.
7. **Is there an infinite source or a filter before matching?** Ensure termination is possible.
8. **Are group boundaries lost by flatMap?** If a proposition is needed per group, preserve the group structure.
9. **Are multiple levels of negation making the condition hard to read?** You can switch `noneMatch(P)` to `allMatch(P.negate())` or vice versa if it reflects the intent better.
10. **Are empty, all-true, all-false, and mixed-data cases tested?** These are the four scenarios that clearly distinguish the three operations.

A good test suite should include **an empty stream** and **at least one element that causes matching to short-circuit**. Both cases catch misunderstandings more often than testing only typical datasets.

## 15. Self-Check Questions

**Question 1.** What does `List.of(1, 2, 3).stream().anyMatch(n -> n % 2 == 0)` return?

**Question 2.** What does `List.of(1, 2, 3).stream().allMatch(n -> n > 0)` return?

**Question 3.** What does `List.of(1, 2, 3).stream().noneMatch(n -> n < 0)` return?

**Question 4.** On an empty stream, why does `allMatch(P)` return true while `anyMatch(P)` returns false?

**Question 5.** `noneMatch(P)` is equivalent to the negation of which method when data and predicate are stable?

**Question 6.** Why should you not perform mandatory audit logging inside the predicate of `anyMatch`?

**Question 7.** When you need to retrieve a record that satisfies a condition instead of a boolean, which API should you use?

**Question 8.** If the business requires “at least one item, and all items are valid”, is using `allMatch` alone enough?

**Question 9.** For an infinite `Stream.generate(() -> 1)`, is `allMatch(n -> n == 1)` guaranteed to terminate?

**Answers:** (1) `true` because `2` is present. (2) `true` because all numbers are positive. (3) `true` because there are no negative numbers. (4) `allMatch` finds no counterexample, whereas `anyMatch` finds no witness element. (5) `!anyMatch(P)`. (6) Short-circuiting may skip many elements; parallel execution even less guarantees order or call counts. (7) `filter(...).findAny()` or `findFirst()` depending on ordering requirements. (8) No, you must check that the source is non-empty. (9) No, because there is no counterexample to conclude false and the source has no stopping point.

## 16. Official References

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): the `anyMatch`, `allMatch`, `noneMatch` methods, short-circuiting terminal operation properties, and empty stream results.
- [Java SE 17 API — Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html): the `test(T)` method along with `negate`, `and`, `or`.
- [Java SE 17 API — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): matching variants for `int` sources.
- [Java SE 17 Package — java.util.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): laziness, non-interference, stateless behavioral parameters, and considerations for parallel processing.

**Key takeaway:** `anyMatch(P)` asks **whether anyone satisfies P**, `allMatch(P)` asks **whether everyone satisfies P**, and `noneMatch(P)` asks **whether no one satisfies P**. For an empty stream, the results are **`false`, `true`, `true`** respectively. All three return `boolean`, short-circuit once enough evidence is found, and **do not guarantee the predicate runs for every element**.