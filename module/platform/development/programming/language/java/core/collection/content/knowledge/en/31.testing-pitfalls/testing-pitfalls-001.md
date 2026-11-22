# Testing Empty, Single-Element, Duplicate-Element, and Null Collections

## 1. What to Test When a Method Accepts a Collection?

A method may work properly with `["A", "B", "C"]` yet fail when given an empty list, a single element, repeated values, or a `null` element. These cases are not merely "rare" inputs. They test the assumptions that code often inadvertently relies on:

- There is always a first or last element.
- A loop always runs at least once.
- Two equal values are always the exact same object.
- Every element is non-`null`.
- The result can be reordered without affecting requirements.
- The function is allowed to mutate the input collection directly.

A valuable test case must define **the input, the action, and the expected result according to the contract**. Merely running the code and seeing "no exception" is not enough to prove that the elements, order, occurrence counts, and side effects are all correct.

This article moves from four groups of boundary data to a standalone runnable Java program, and then translates the same ideas into JUnit 5 tests.

## 2. Write the Contract Before Writing Expected Results

### 2.1. There Is No Single Universal Answer for Every Collection

Consider the input `["A", "A", null]`. A function might:

- Keep all three elements as-is.
- Drop the `null` element, but keep both occurrences of `"A"`.
- Drop `null` and keep only the first occurrence of `"A"`.
- Reject an input containing `null` with a specified exception.

All of these choices can be valid in different problems. A test must not decide the policy on its own in place of the function's contract.

Before preparing test data, answer the following:

| Aspect | Question to Clarify |
| --- | --- |
| Input collection | Is passing `null` allowed, or must a non-null collection be passed? |
| Empty | Return an empty result, a default value, or report a business error? |
| Null elements | Retain, ignore, convert to another value, or reject? |
| Duplicate elements | Keep all occurrences, deduplicate, or aggregate? |
| Ordering | Preserve input order, sort, or provide no guarantee? |
| Side effects | Is mutating the source allowed? Does the result share structure with the source? |
| Mutability | Does the result allow adding/removing elements, or must it be unmodifiable? |

Not every contract needs every row, but the relevant rows must be clear before writing assertions.

### 2.2. Sample Contract Used in This Article

We will test the function:

```text
distinctNonNull(Collection<String> source) -> List<String>
```

The sample function has a specific contract:

1. `source == null` is rejected with a `NullPointerException`.
2. An empty collection produces an empty list.
3. `null` elements are ignored.
4. Duplicate values are determined by `String.equals()` and kept only once.
5. The result preserves the first-seen order when traversing the source.
6. The source collection is not modified.
7. The result is a new list that supports adding/removing elements; structural changes to the source and the result do not propagate to each other.
8. Whitespace is not trimmed and letter case is not changed. `"A"`, `"a"`, `""`, and `" "` are distinct values.

This is the policy for our example, not a mandatory rule for every collection-processing function. If the source is a `HashSet` with no iteration order guarantee, the function cannot fabricate an "original insertion order" guarantee that the source itself does not provide. The order-checking test cases in this article use a `List` source with a well-defined order.

## 3. The Empty Group: Having No Elements Is Still a Valid State

### 3.1. Distinguishing an Empty Collection from a Null Collection

```text
[]      : a collection object exists, size is 0
null    : no reference to a collection object
[null]  : a collection exists, size is 1, the sole element is null
```

These three inputs test three different things. Do not lump them into a single test case named "no data" if the contract distinguishes between them.

For the sample function:

| Input | Expected Result |
| --- | --- |
| `[]` | `[]` |
| `null` | Throws `NullPointerException` |
| `[null]` | `[]` because the policy ignores null elements |

### 3.2. Bugs Commonly Caught by Empty Test Cases

- Calling `get(0)` before checking the size.
- Initializing the result from the first element without a branch to handle an empty collection.
- Returning `null` instead of an empty collection when the contract requires a collection.
- Calculating an average by dividing by a size of `0`.
- Returning an unmodifiable empty list in the empty branch while the non-empty branch returns a mutable list and the contract requires consistency.

For the sample function, checking `result.isEmpty()` is not enough for the full contract. We also need to know that `result` is non-null, allows adding elements, and that adding to it does not change the source.

Do not call every mutating operation on every empty collection and assume it will succeed. Mutability depends on the collection type and its specific contract.

## 4. The Single-Element Group: Testing Loop Boundaries and Initialization Branches

Single-element test data helps catch bugs such as:

- A loop using `i < size - 1`, thereby skipping the last element.
- Starting iteration at index `1`, thereby processing no elements at all.
- Code always accessing the next element even when none exists.
- A "nothing to deduplicate" branch returning the source directly, causing the source and result to share structure.

Under the sample contract, `List.of("A")` must produce the result `["A"]`. However, comparing contents alone will not detect whether the function returned the source list as-is.

If the contract requires a new result, verify the behavior after structural modification:

1. Call the function with a single-element source.
2. Add an element to the result.
3. Confirm that the source still contains only the original element.

Checking for distinct references can be supplementary, but independent mutation behavior clearly expresses the intent of the requirement. Do not test object identity when the contract only promises equivalent values.

## 5. The Duplicate Group: Count, Position, and the Notion of Equality

### 5.1. Use Both Adjacent and Separated Duplicates

Testing only `["A", "A"]` can miss an algorithm that only removes adjacent duplicates. Add a case such as:

```text
Source: ["B", "A", "B", "C", "A"]
Result: ["B", "A", "C"]
```

This case simultaneously tests:

- Deduplication even when two occurrences are not adjacent.
- Not accidentally dropping other values.
- Preserving first-occurrence order rather than sorting into `["A", "B", "C"]`.

If the contract requires keeping every occurrence, the expectation must differ. For example, a list-copying function must keep `["A", "A"]` and must not turn it into a set on its own.

### 5.2. Value Equality Does Not Imply Reference Identity

A test using only string literals might inadvertently fail to catch code that uses `==` to compare strings. Create two distinct objects that are equal in value:

```java
String first = new String("A");
String second = new String("A");
```

This is illustrative test data designed to check the difference between reference identity and value equality, not a string instantiation pattern to use routinely in application code.

Under the sample contract, both produce only a single `"A"` value in the result. For custom classes, you must verify that `equals()` and `hashCode()` are properly implemented if hash-based collections are used. If the domain uses a different rule, such as case-insensitive comparison, include that rule in both the contract and the test data.

### 5.3. There Is No Single Duplicate Rule Across List, Set, and Map

| Structure | What Should "Duplicate" Be Tested Against? |
| --- | --- |
| General `List` | Can hold multiple equal elements; both order and occurrence count matter |
| `HashSet` | Equal elements do not add a new entry; requires a proper `equals/hashCode` contract |
| General `Map` | Keys are unique; two distinct keys can still map to the same value |
| `TreeSet`/`TreeMap` | Determining whether keys/elements occupy the same position relies on ordering comparison; test the domain's comparison rules; see [TreeSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) |

Do not use `toString()` to turn every collection into a string for comparison. Doing so easily couples the test to display formatting or unguaranteed ordering rather than the semantics being verified.

## 6. The Null Group: Testing the Right Layer and the Right API

### 6.1. Choosing a Data Construction Method That Allows Nulls

The following snippet fails to create a list containing `null`:

```java
List<String> input = List.of("A", null, "B");
```

`List.of` rejects `null` elements, so the exception occurs during input preparation, before the function under test is ever called. `List.of` still allows duplicate elements; duplicate rules and null rules are separate concerns. [Java 17 List Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

To create a source containing nulls for our example, you can use:

```java
List<String> input = new ArrayList<>(
        Arrays.asList("A", null, "B", null));
```

This snippet requires importing `java.util.List`, `java.util.ArrayList`, and `java.util.Arrays`. `Arrays.asList` permits null elements but has a fixed size; wrapping it with `new ArrayList<>(...)` creates a list that supports adding and removing elements. If the data is only read, this wrapper is not always necessary.

For a single null element, you can use `Collections.singletonList(null)` with an appropriate type witness, or create a list and call `add(null)`. Avoid the ambiguous varargs expression `Arrays.asList(null)`: `null` can be interpreted as the varargs array reference itself. `Arrays.asList((String) null)` clearly expresses a single `String` element whose value is `null`.

### 6.2. Testing Meaningful Null Positions

Depending on the algorithm, choose cases likely to trigger different branches:

- Null at the beginning: `[null, "A"]`.
- Null in the middle: `["A", null, "B"]`.
- Null at the end: `["A", null]`.
- Only nulls: `[null]` or `[null, null]`.
- Nulls interleaved with duplicates: `[null, "A", null, "A", "B"]`.

It is not necessary to enumerate every permutation. Pick representatives targeting the code's assumptions, then add combined cases where factors might interact.

### 6.3. Null Policy Depends on the Implementation

`HashSet` permits a null element, with at most one null element in the set. `HashMap` permits a null key and null values. Neither property should be generalized to every `Set` or every `Map`. [HashSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [HashMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

`Set.of` rejects nulls and rejects duplicate elements when creating a set. `Map.of` rejects null keys/values and duplicate keys when creating a map. Unlike `HashMap.put`, passing duplicate keys to `Map.of` is not a request to overwrite the old value. [Set Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

`ArrayDeque` does not permit null elements. When testing queues, you must also separate the empty state from the element policy; for instance, `poll()` returns `null` when no element is available to retrieve. [ArrayDeque Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

### 6.4. Map: A Null Value Is Different from an Absent Key

For a `HashMap` that can hold null values:

```text
get("known")   -> null, even though key "known" has a mapping
get("missing") -> null, because key "missing" is not present
```

If the requirements need to distinguish between these two states, check `containsKey()` as well. Calling `assertNull(map.get(key))` alone cannot tell them apart.

For wrapper numbers, a null `Integer` element can also cause a `NullPointerException` when unboxed for addition or comparison using numeric operators. Tests must exercise the operations that consume the elements, not just confirm that the collection can hold `null`.

## 7. Test Matrix for the Sample Function

The expected results below are derived from the contract in Section 2, before looking at the implementation.

| Case | Source | Expected | Potential Bug Detected |
| --- | --- | --- | --- |
| Empty | `[]` | `[]` | Accessing a non-existent first element |
| Single element | `["A"]` | `["A"]` | Dropping the sole element |
| Adjacent duplicates | `["A", "A"]` | `["A"]` | Failing to deduplicate |
| Separated duplicates | `["B", "A", "B", "C", "A"]` | `["B", "A", "C"]` | Deduplicating only adjacent items; wrong ordering |
| Interleaved nulls | `[null, "A", null, "B", "A"]` | `["A", "B"]` | Calling a method on null; wrong combined policy |
| Only nulls | `[null, null]` | `[]` | Retaining null against the contract |
| Two objects equal by value | Two `new String("A")` | `["A"]` | Using `==` instead of `equals()` |
| No extra normalization | `["", " ", "", "a", "A"]` | `["", " ", "a", "A"]` | Unwanted whitespace trimming or case conversion |
| Entire source is null | `null` | `NullPointerException` | Confusing a null source with an empty source |
| Source and result independence | Mutate structure of each side after the call | Both sides remain independent | Returning the source as-is or returning a view |

For easier diagnosis, initial test cases should focus on one rule at a time. Then use combined data to catch interaction bugs. A single test case stuffed with every factor is a poor substitute for focused test cases.

## 8. Self-Checking Java 17+ Program

The program below requires no external libraries. It uses helper methods that throw `AssertionError` on failure, so it does not depend on enabling the `-ea` flag for Java's `assert` keyword.

`LinkedHashSet` stores unseen values in first-traversal order; the result is copied into a new `ArrayList`. A concise implementation does not replace contract tests. [LinkedHashSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Save as `CollectionBoundaryDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class CollectionBoundaryDemo {
    private static int passed;

    static List<String> distinctNonNull(Collection<String> source) {
        Objects.requireNonNull(source, "source");
        Set<String> unique = new LinkedHashSet<>();
        for (String value : source) {
            if (value != null) {
                unique.add(value);
            }
        }
        return new ArrayList<>(unique);
    }

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectThrows(String label,
                                     Class<? extends Throwable> expected,
                                     Runnable action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError(label + ": wrong exception", actual);
            }
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected " + expected.getSimpleName());
    }

    public static void main(String[] args) {
        checkEquals("empty", List.of(), distinctNonNull(List.of()));
        checkEquals("singleton", List.of("A"), distinctNonNull(List.of("A")));
        checkEquals("adjacent duplicates", List.of("A"),
                distinctNonNull(List.of("A", "A")));
        checkEquals("separated duplicates and order", List.of("B", "A", "C"),
                distinctNonNull(List.of("B", "A", "B", "C", "A")));
        checkEquals("nulls and duplicates", List.of("A", "B"),
                distinctNonNull(Arrays.asList(null, "A", null, "B", "A")));
        checkEquals("only nulls", List.of(),
                distinctNonNull(Arrays.asList((String) null, (String) null)));
        checkEquals("equal values in separate objects", List.of("A"),
                distinctNonNull(List.of(new String("A"), new String("A"))));
        checkEquals("no extra normalization", List.of("", " ", "a", "A"),
                distinctNonNull(List.of("", " ", "", "a", "A")));
        expectThrows("null source", NullPointerException.class,
                () -> distinctNonNull(null));

        List<String> source = new ArrayList<>(Arrays.asList("A", null, "A", "B"));
        List<String> before = new ArrayList<>(source);
        List<String> result = distinctNonNull(source);
        checkEquals("source unchanged by call", before, source);
        checkEquals("result content", List.of("A", "B"), result);
        result.add("C");
        checkEquals("result is mutable", List.of("A", "B", "C"), result);
        checkEquals("result mutation does not change source", before, source);
        source.add("D");
        checkEquals("source mutation does not change result",
                List.of("A", "B", "C"), result);
        List<String> emptyResult = distinctNonNull(List.of());
        emptyResult.add("X");
        checkEquals("empty result is also mutable", List.of("X"), emptyResult);

        expectThrows("List.of rejects null", NullPointerException.class,
                () -> List.of("A", (String) null));
        expectThrows("Set.of rejects duplicates", IllegalArgumentException.class,
                () -> Set.of("A", "A"));
        expectThrows("Map.of rejects duplicate keys", IllegalArgumentException.class,
                () -> Map.of("A", 1, "A", 2));
        expectThrows("ArrayDeque rejects null", NullPointerException.class,
                () -> new ArrayDeque<String>().add(null));

        Set<String> nullableSet = new HashSet<>(
                Arrays.asList("A", "A", null, "B", null));
        checkEquals("HashSet removes duplicates including null", 3, nullableSet.size());
        checkEquals("HashSet contains null", true, nullableSet.contains(null));

        Map<String, String> nullableMap = new HashMap<>();
        nullableMap.put(null, "fallback");
        nullableMap.put("known", null);
        checkEquals("HashMap null key", "fallback", nullableMap.get(null));
        checkEquals("present null value", null, nullableMap.get("known"));
        checkEquals("missing key lookup", null, nullableMap.get("missing"));
        checkEquals("known key exists", true, nullableMap.containsKey("known"));
        checkEquals("missing key does not exist", false,
                nullableMap.containsKey("missing"));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Compile and run:

```shell
javac --release 17 CollectionBoundaryDemo.java
java CollectionBoundaryDemo
```

Stdout when all checks pass:

```text
PASS: 26 checks
```

If any check fails, the program terminates with an `AssertionError` rather than printing the PASS line. The API checks in the latter part of `main` are conceptually separate from the sample function checks: they confirm how test data is prepared and demonstrate the differences across specific collection implementations.

Catching `Throwable` here is confined to a small test utility to verify the thrown exception type; it is not advice to catch and ignore all errors in business code. JVM exception messages are not used as pass criteria because message wording can vary across environments.

## 9. Translating the Same Matrix to JUnit 5

In a project with JUnit Jupiter available, use parameterized tests to keep a single assertion structure while supplying multiple source/expected pairs. `@MethodSource` is convenient when each case involves complex collections or nulls; exception tests should reside in a dedicated test method. [JUnit 5 User Guide on MethodSource](https://docs.junit.org/5.10.2/user-guide/#writing-tests-parameterized-tests-sources-MethodSource)

The snippet below is an illustrative test class for an environment configured with `junit-jupiter-api`, `junit-jupiter-params`, and the JUnit Jupiter engine at runtime. It is not a standalone program executed directly via the `java` command as in Section 8. Place it in the same package as `CollectionBoundaryDemo` or adjust the method's visibility in production code.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class CollectionBoundaryTest {
    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(List.of(), List.of()),
                Arguments.of(List.of("A"), List.of("A")),
                Arguments.of(List.of("B", "A", "B", "C"), List.of("B", "A", "C")),
                Arguments.of(Arrays.asList(null, "A", null, "A"), List.of("A")),
                Arguments.of(Arrays.asList((String) null, (String) null), List.of()));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void followsValueContract(List<String> input, List<String> expected) {
        List<String> before = new ArrayList<>(input);
        List<String> actual = CollectionBoundaryDemo.distinctNonNull(input);
        assertEquals(expected, actual);
        assertEquals(before, input);
    }

    @Test
    void rejectsNullCollection() {
        assertThrows(NullPointerException.class,
                () -> CollectionBoundaryDemo.distinctNonNull(null));
    }
}
```

`assertEquals` on two `List` instances checks contents in order, making it well suited for an order-preserving contract. Test cases for mutability and structural independence should be written as separate dedicated tests similar to the full standalone program, rather than assuming the parameter table above covers the entire contract.

If you use `@NullSource`, remember that it supplies a `null` argument to the test method itself; it does not create a list containing a single `null` element. Those two scenarios require different input data.

## 10. Choosing Assertions According to the Semantics Being Protected

### 10.1. List: Contents, Order, and Occurrence Count

If the result is an ordered list, compare it directly against an expected `List`. Checking only `size()` fails to detect substituted elements or inverted order. Checking only `contains()` fails to detect an extra duplicate or a missing occurrence.

For example, `["A", "A", "B"]` and `["A", "B", "B"]` have the same size and the same set of values, but not the same occurrence counts. Do not convert both into a `Set` and conclude they are equivalent if repetition counts are part of the contract.

### 10.2. Set: Do Not Rely on Order When It Is Not Guaranteed

For a set without ordering guarantees, compare the element sets using `Set.equals()`. Do not require a `HashSet` to print an exact string matching whatever iteration order happened to appear on your machine.

If the contract requires a specific traversal order, choose a collection with the appropriate guarantee and test traversal order explicitly. `Set.equals()` by itself does not verify order.

### 10.3. Map: Test Mappings, Not Just the Value Set

Two maps can have the exact same set of values while pairing them with different keys. Compare the maps directly or assert each required key-value mapping. When `null` is allowed, include `containsKey()` if you need to distinguish a missing key from a key mapped to a `null` value.

When reinserting an existing key, check the final value, the map size, and the returned previous value if those are part of the behavior being protected. Do not confuse "duplicate values" with "duplicate keys".

### 10.4. Exceptions: Scope the Exact Action Under Test

A test expecting `NullPointerException` can pass by accident if the error occurs during test data preparation rather than because the function under test rejected the input.

Construct valid test data first, then wrap only the target invocation inside `assertThrows`. Place data creation inside the expected-exception block only when the factory itself is the subject under test, as in the `List.of` checks in the sample program.

Do not catch an exception just to print a message. If the error does not occur or has the wrong type, the test must fail clearly.

## 11. Common Test Design Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Testing only lists with multiple distinct values | Misses empty, singleton, duplicate, and null branches | Establish representative boundary data groups first |
| Using `List.of` to build test data containing `null` | Fails before calling the function under test | Use a data construction method with an appropriate null policy |
| Checking only the collection size | Fails to detect wrong elements or wrong order | Assert contents according to the result's semantics |
| Converting list results to `Set` for comparison | Loses occurrence count and ordering information | Keep `List` comparisons when the contract specifies a list |
| Computing `expected` using the exact algorithm under test | Both share the same bug and the test still passes | Write independent expected values directly from the contract |
| Reusing a single mutable collection across multiple test cases | Earlier cases mutate the input data of later cases | Create a fresh source for each test case whenever mutation is possible |
| Testing only whether a collection accepts `null` | Misses errors when null elements are actually consumed | Exercise the downstream processing operations as well |
| Forcing every function to treat `null` as empty | Masks contract violations or loses business distinction | Uphold the specified null policy |
| Requiring a specific concrete implementation class beyond the contract | Tests break when switching to an equivalent implementation | Test published behaviors and guarantees |

A shallow input copy via `new ArrayList<>(source)` is sufficient to snapshot structure and references for the `String` example in this article. For mutable elements, a shallow copy will not catch internal state mutations inside the elements themselves; capture the value state that needs protection or use appropriate immutable data.

## 12. Self-Check and Exercises

### Question 1: Is a function that returns an empty list for a null input always correct?

No. It is correct only when the contract defines `null` as equivalent to having no elements. The sample function in this article requires rejecting `null`, so returning an empty list would be wrong even though no exception is thrown.

### Question 2: Does a deduplication function that returns `["A", "B", "C"]` for `["B", "A", "B", "C"]` pass?

It fails the sample contract because it altered the first-seen order. It could pass a different contract that requires a sorted result. Assertions must follow the specific contract under test.

### Question 3: Does `map.get(key) == null` prove that the key is absent?

Not for a map that permits null values. You must check `containsKey(key)` if that distinction matters.

### Question 4: Has a test that calls `List.of("A", null)` and observes a `NullPointerException` tested how the function handles null?

Not yet. The factory failed before the function ever received the data. Build a null-containing source using an appropriate API and scope the assertion around the exact target action.

### Practice Exercises

1. Add test cases for a single null element, null only at the start, and null only at the end for the sample function; write the expected results before running them.
2. Change the sample contract to "retain null elements as well, but deduplicate them", and identify the exact test cases whose expected outputs must change. Do not update expectations merely by copying new output from the program.
3. Write test cases for a frequency-counting function where `["A", "A", "B"]` must produce counts `A=2`, `B=1`; decide the null policy first.
4. Create a test with a single-element input, mutate the result after the call, and verify that the source remains independent according to the contract.

The four boundary data groups are a starting point for uncovering hidden assumptions. A trustworthy test suite also protects the contents, order, occurrence counts, null policy, and side effects that callers are actually promised.
