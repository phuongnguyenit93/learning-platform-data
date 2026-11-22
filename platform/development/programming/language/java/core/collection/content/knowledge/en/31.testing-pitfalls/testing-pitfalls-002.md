# Testing the equals–hashCode and Comparator Contracts

## 1. Why Do Collections Expose Object Bugs?

An object might print the expected data yet still fail to be found in a `HashSet`. Two distinct records might collapse into a single element when added to a `TreeSet`. A comparator might sort a few small numbers correctly and then fail on boundary values.

These symptoms usually stem from the equality or ordering relationships provided by the object class. Collections rely on these relationships to search, deduplicate, replace, or sort elements.

Two distinct layers of requirements need to be tested:

1. **Java contract laws**: reflexivity, symmetry, transitivity, consistency, and the relationships between results.
2. **Domain semantics**: which fields define two records as equal, which sort precedence is right, and whether ties should be merged into a single element.

An `equals` implementation that only compares reference identity can still satisfy the general contract laws, yet be wrong if the application requires equality by code and version. Similarly, a comparator that only compares scores can be valid as an ordering relation yet unsuitable for distinguishing records in a `TreeSet`.

## 2. Turning the equals Contract into Test Cases

For non-`null` references `a`, `b`, and `c` in the domain under test:

| Law | What to Check | Required Data |
| --- | --- | --- |
| Reflexivity | `a.equals(a)` is `true` | Every sample object |
| Symmetry | `a.equals(b)` equals `b.equals(a)` | Equal pairs, unequal pairs; pay attention to inheritance if supported |
| Transitivity | If `a.equals(b)` and `b.equals(c)`, then `a.equals(c)` | Three distinct object references with the same value considered equal |
| Consistency | Repeated calls return the same result when relevant information does not change | Keep state unchanged during verification |
| Non-nullity | `a.equals(null)` is `false` | A valid object and `null` |

This is the contract of [Object.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)). Do not call `null.equals(...)`; that dereferences a `null` reference rather than testing an `equals` law.

### 2.1. Do Not Let the Transitivity Test Become Vacuous

If the sample set only contains completely distinct objects, the premise `a.equals(b) && b.equals(c)` is almost always false. The verification loop still runs and reports PASS, but it never actually exercises an equivalence group.

Deliberately construct:

- Three distinct instances belonging to the same group of equal values.
- Instances that differ by only one equality-significant field at a time.
- Instances that differ only in fields excluded from equality, if the model has such fields.
- Foreign types, or subclass and superclass instances if the design permits and needs to support them.

A pair of "two variables pointing to the same object" does not replace a pair of "two independent objects with the same value." Many bugs only surface when data is reloaded from a file, database, or API into a new instance.

### 2.2. Business Expectations Must Be Independent of the Code Under Test

If a `Key(id, score)` class is defined as equal when both `id` and `score` are equal, state the expectations explicitly:

```text
Key(A, 0) and Key(A, 0): equal, even as distinct instances
Key(A, 0) and Key(B, 0): not equal
Key(A, 0) and Key(A, 1): not equal
```

Do not build expected values by calling `equals` itself or using a `Set` as the sole "ground truth." Doing so can make the test merely repeat the bug in the very relationship being verified.

## 3. Testing hashCode in the Right Direction of Implication

The required relationship is:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

The converse does not hold. Two unequal objects may share the same hash code; that is a hash collision, not automatically a contract violation.

Within the same execution, repeated calls to `hashCode` must return the same result as long as information used in `equals` checks is not modified. Do not assert that a specific hash value must remain identical across every JVM execution. [Object.hashCode contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()).

### Assertions to Avoid

- `a` is not equal to `b`, so their hashes must be different.
- The hash of this object must always match a hardcoded number captured from a previous run, when the API does not guarantee a specific algorithm.
- Two objects have the same hash, so they must be `equals`.
- A well-distributed hash alone proves that the `equals` relationship is right.

Hash distribution quality is a separate performance concern. A function that always returns `0` can still satisfy the contract if `equals` is properly implemented, though it causes heavy collisions and is usually a poor performance choice.

### Verifying Through Hash-Based Collections

Starting with two distinct instances that are equal according to the contract:

1. Add the first instance to a `HashSet`.
2. Add the second instance and verify that the size does not increase.
3. Use another equal instance to verify `contains` and `remove`.
4. With a `HashMap`, put a value using the first key, look up or replace it using an equal key, and verify that the map still contains only one mapping for that key.

These tests confirm the integration behavior that the application actually relies on. They complement direct law checks rather than replacing domain fixtures.

## 4. Comparator: Check the Sign, Do Not Memorize -1 and 1

`compare(a, b)` returns a negative integer, zero, or a positive integer. The contract does not require every comparator to return only `-1`, `0`, or `1`. When verifying relationships, inspect the sign of the result.

Let `s(a,b) = Integer.signum(comparator.compare(a,b))`. The core requirements are:

| Property | Check |
| --- | --- |
| Self-comparison | `compare(a,a) == 0` |
| Antisymmetry (reversing order flips sign) | `s(a,b) == -s(b,a)` |
| Order transitivity | If `compare(a,b) > 0` and `compare(b,c) > 0`, then `compare(a,c) > 0` |
| Tied elements must behave identically | If `compare(a,b) == 0`, then `s(a,c) == s(b,c)` for every `c` in the domain |
| Stability when inputs and criteria are unchanged | Repeated calls do not flip the less-than/equal/greater-than relationship |

If comparing a pair throws an exception, reversing the order of that pair must also throw an exception according to the contract. Unsupported domain inputs, such as `null`, should be tested separately according to the published policy. [Comparator.compare contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html#compare(T,T)).

Do not write `compare(a,b) == -compare(b,a)` on raw integer values. That requirement is stricter than the contract, and negating the value can overflow at `Integer.MIN_VALUE`. Normalizing to the sign before comparing avoids this testing pitfall.

### 4.1. Subtraction Overflow Only Surfaces at Boundary Values

The following comparator is unsafe:

```java
Comparator<Integer> broken = (left, right) -> left - right;
```

When subtraction overflows `int`, the sign can be wrong. With `left = Integer.MIN_VALUE` and `right = 0`, the result is negative; reversing the direction to compute `0 - Integer.MIN_VALUE` also overflows and remains negative. The two directions no longer produce opposite signs.

Use `Integer.compare(left, right)`, `Comparator.naturalOrder()`, or `Comparator.comparingInt(...)` as appropriate for the data type. For `long`, use a `long` comparison mechanism rather than casting the difference down to `int`.

### 4.2. Testing Precedence and Tie-Breaking

The comparator `comparingInt(Key::score).thenComparing(Key::id)` compares scores first; only when scores are equal does it compare IDs. Prepare pairs with the same score and different IDs, the same ID and different scores, and extreme score values.

Adding `thenComparing` is only right if the secondary criterion matches the requirements. You cannot assume an arbitrary comparator chain is consistent with `equals` just because it has a tie-breaker; you must check whether the `compare == 0` equivalence group coincides with the `equals` group.

## 5. Consistency with equals Is a Requirement to Test Separately

The condition for consistency with `equals` is:

```text
(compare(a,b) == 0) == a.equals(b)
```

In general, a comparator can be inconsistent with `equals` and still satisfy the ordering laws. However, when used with a `TreeSet` or for `TreeMap` keys, inconsistency can cause the collection to deviate from the general `Set`/`Map` contract defined in terms of `equals`. `TreeSet` determines whether two elements occupy the same position via comparison, not via an independent `equals` call. [TreeSet documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

For example, consider two `Key` instances that share score `0` but have IDs `A` and `B`:

- `equals` across both fields returns `false`.
- A score-only comparator returns `0` and remains valid under the comparator laws.
- A `TreeSet` using the score-only comparator will retain only one element after adding both.

If the goal is merely sorting a `List` by score, ties across different IDs may be intentional. If both IDs must be retained in a `Set`, you must choose an ordering relation that matches the identity the `Set` is meant to represent.

### BigDecimal Is a Real-World Example

`new BigDecimal("1.0")` and `new BigDecimal("1.00")` are equal in numerical value under `compareTo`, whereas `equals` also distinguishes scale. Consequently, a hash set and a natural-order tree set can end up with different element counts when both values are inserted. This is documented behavior, not proof that the collection is broken. [BigDecimal documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

When testing, determine whether the application treats scale as meaningful information or cares only about numerical value. Do not alter that relationship implicitly when switching collection types.

## 6. Java 17+ Law-Based Verification Program

The program below uses a `check` helper that throws `AssertionError`, so the `-ea` flag is not required. It requires no JUnit or external libraries. Save it as `ContractChecks.java`.

Example contract: `Key` has a non-`null` `id`; both `id` and `score` participate in `equals`. The full comparator compares `score` and then `id`. All samples remain unmodified throughout verification.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ContractChecks {
    record Key(String id, int score) {
        Key {
            Objects.requireNonNull(id);
        }
    }

    record CollisionKey(int value) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static <T> void verifyEquality(List<T> samples) {
        for (T a : samples) {
            check(a != null, "use non-null equality samples");
            check(a.equals(a), "reflexivity: " + a);
            check(!a.equals(null), "null equality: " + a);
            int hash = a.hashCode();
            for (T b : samples) {
                boolean equal = a.equals(b);
                check(equal == b.equals(a), "symmetry: " + a + ", " + b);
                if (equal) {
                    check(a.hashCode() == b.hashCode(), "equal objects need equal hashes");
                }
                for (int repeat = 0; repeat < 3; repeat++) {
                    check(a.equals(b) == equal, "unstable equality");
                    check(a.hashCode() == hash, "unstable hash without mutation");
                }
                for (T c : samples) {
                    if (equal && b.equals(c)) {
                        check(a.equals(c), "transitivity: " + a + ", " + b + ", " + c);
                    }
                }
            }
        }
    }

    static <T> void verifyComparator(
            List<T> samples, Comparator<T> comparator, boolean consistentWithEquals) {
        for (T a : samples) {
            check(comparator.compare(a, a) == 0, "compare self");
            for (T b : samples) {
                int ab = Integer.signum(comparator.compare(a, b));
                int ba = Integer.signum(comparator.compare(b, a));
                check(ab == -ba, "opposite signs: " + a + ", " + b);
                if (consistentWithEquals) {
                    check((ab == 0) == Objects.equals(a, b), "compare zero versus equals");
                }
                for (int repeat = 0; repeat < 3; repeat++) {
                    check(Integer.signum(comparator.compare(a, b)) == ab, "unstable order");
                }
                for (T c : samples) {
                    int bc = Integer.signum(comparator.compare(b, c));
                    int ac = Integer.signum(comparator.compare(a, c));
                    if (ab > 0 && bc > 0) {
                        check(ac > 0, "order transitivity: " + a + ", " + b + ", " + c);
                    }
                    if (ab == 0) {
                        check(ac == bc, "zero group must compare alike against third value");
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A", 0);
        Key b = new Key("A", 0);
        Key c = new Key("A", 0);
        Key otherId = new Key("B", 0);
        Key otherScore = new Key("A", 1);
        List<Key> samples = List.of(
                a, b, c, otherId, otherScore,
                new Key("MIN", Integer.MIN_VALUE),
                new Key("MAX", Integer.MAX_VALUE));

        check(a != b && a.equals(b), "equal values must include distinct instances");
        check(!a.equals(otherId), "id belongs to equality");
        check(!a.equals(otherScore), "score belongs to equality");
        check(!a.equals("A"), "foreign type");
        verifyEquality(samples);
        System.out.println("equals/hashCode=PASS");

        Set<Key> hashSet = new HashSet<>();
        check(hashSet.add(a), "first insertion");
        check(!hashSet.add(b), "equal insertion must not grow set");
        check(hashSet.contains(c), "lookup through equal distinct object");
        check(hashSet.remove(c) && hashSet.isEmpty(), "remove through equal object");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "first");
        check("first".equals(map.put(b, "found")) && map.size() == 1, "equal key replaces value");
        check("found".equals(map.get(c)), "map lookup through equal object");
        check("found".equals(map.remove(c)) && map.isEmpty(), "map remove through equal object");
        System.out.println("hash collection lookup=PASS");

        Comparator<Key> byScore = Comparator.comparingInt(Key::score);
        Comparator<Key> byScoreThenId = byScore.thenComparing(Key::id);
        verifyComparator(samples, byScore, false);
        verifyComparator(samples, byScoreThenId, true);
        System.out.println("comparator laws=PASS");

        List<Key> sorted = new ArrayList<>(List.of(otherScore, otherId, a));
        sorted.sort(byScoreThenId);
        check(sorted.equals(List.of(a, otherId, otherScore)), "expected business order");
        System.out.println("ordered=" + sorted.stream()
                .map(key -> key.id() + ":" + key.score())
                .toList());

        Set<Key> coarse = new TreeSet<>(byScore);
        coarse.add(a);
        coarse.add(otherId);
        Set<Key> precise = new TreeSet<>(byScoreThenId);
        precise.add(a);
        precise.add(otherId);
        System.out.println("score-only tree size=" + coarse.size());
        System.out.println("score-and-id tree size=" + precise.size());

        List<Key> nullableSamples = new ArrayList<>(samples);
        nullableSamples.add(null);
        verifyComparator(nullableSamples, Comparator.nullsFirst(byScoreThenId), true);
        System.out.println("nullsFirst policy=PASS");

        boolean rejected = false;
        try {
            verifyComparator(
                    List.of(Integer.MIN_VALUE, 0, Integer.MAX_VALUE),
                    (left, right) -> left - right,
                    true);
        } catch (AssertionError ex) {
            rejected = true;
        }
        check(rejected, "subtraction comparator should fail on boundary values");
        System.out.println("subtraction comparator rejected=" + rejected);

        CollisionKey x = new CollisionKey(1);
        CollisionKey y = new CollisionKey(2);
        verifyEquality(List.of(x, new CollisionKey(1), y));
        Set<CollisionKey> collisions = new HashSet<>(List.of(x, y));
        check(collisions.size() == 2, "collision must not merge unequal objects");
        System.out.println("collision set size=" + collisions.size());

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal anotherOne = new BigDecimal("1.00");
        System.out.println("decimal equals=" + one.equals(anotherOne));
        System.out.println("decimal compare zero=" + (one.compareTo(anotherOne) == 0));
        System.out.println("decimal hash set size=" + new HashSet<>(List.of(one, anotherOne)).size());
        System.out.println("decimal tree set size=" + new TreeSet<>(List.of(one, anotherOne)).size());
    }
}
```

Compile and run:

```shell
javac --release 17 ContractChecks.java
java ContractChecks
```

Exact stdout:

```text
equals/hashCode=PASS
hash collection lookup=PASS
comparator laws=PASS
ordered=[A:0, B:0, A:1]
score-only tree size=1
score-and-id tree size=2
nullsFirst policy=PASS
subtraction comparator rejected=true
collision set size=2
decimal equals=false
decimal compare zero=true
decimal hash set size=2
decimal tree set size=1
```

### 6.1. What Does Each Test Group Prove?

- Three `Key("A", 0)` instances provide a genuine equivalence group to test transitivity, symmetry, and hash consistency.
- Cases differing only in `id` or `score` encode explicit domain expectations rather than checking abstract laws alone.
- `HashSet` and `HashMap` are accessed through equal but distinct object references; the map test also verifies value replacement and removal via an equal key.
- The score-only comparator is verified against the laws with the `false` flag because it is not required to be consistent with `equals` in that check.
- The score-then-ID comparator is verified with the `true` flag, adding the requirement that `compare == 0` matches `equals`.
- The sorted list is checked against an independently written expected order, rather than generating the expected result by sorting with the same comparator.
- `CollisionKey` deliberately returns hash `0` for every value while still distinguishing values in `equals`. The `Set` must retain both `1` and `2`.
- The subtraction comparator is tested with extreme values and caught violating the contract; the program does not wait for a sorting algorithm to happen to throw an error.

### 6.2. Program Limitations

The test suite examines only a finite set of samples. A `PASS` does not prove that the contract holds for every object that could possibly be created. Calling methods three times in a row is merely a practical check for stability on the samples, not a proof that a function has no hidden state dependencies.

Both verification methods use triple-nested loops with O(s³) complexity in the number of samples `s`. They are intended for small fixture sets in tests, not for running across millions of objects on a production hot path.

`verifyEquality` takes non-`null` samples and tests `a.equals(null)` internally. `verifyComparator` treats the samples as the allowed comparison domain; a comparator that rejects `null` requires a separate exception test case. This harness does not automatically generate every possible foreign class or exception type that might be passed to `equals`.

## 7. Null Policy and Data Stability

### 7.1. Does the Comparator Allow or Reject null?

`Comparator.nullsFirst(base)` and `nullsLast(base)` add a policy for `null` element references. In the example, `nullsFirst` is tested with both `null` and valid `Key` instances.

Distinguish a `null` element from a `null` field inside an element. Wrapping an outer comparator with `nullsFirst` does not automatically make extracting a `key.id()` that returns `null` safe for natural string comparison. If a field is allowed to be `null`, provide a null-safe comparator for that field itself or define an explicit normalization rule.

If the policy is to reject `null`, assert the expected exception for both `compare(null, a)` and `compare(a, null)` according to the contract. Do not turn an expected exception case into a "skipped test."

### 7.2. Do Not Assert Results After Violating Collection Usage Preconditions

An object may mutate fields used by `equals`/`hashCode`. However, mutating those fields while the object is an element of a hash-based `Set` or a key in a `Map` breaks the precondition the collection relies on. The `Set` documentation warns that behavior is not specified if an element is mutated in a manner that affects `equals` comparisons while the element is in the set. [Set documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

Similarly, mutating a sort field while an element resides in a tree structure can leave the stored order out of sync with the current comparator. Do not write a test demanding that `contains` always return a specific value after such invalid usage.

Testing the design itself is usually much more useful:

- Immutable keys are constructed properly and do not expose internal mutable component objects to unintended modification.
- If key changes are needed, the domain workflow removes the object from the collection before mutating it and reinserts it properly afterward.
- Purely descriptive fields either participate or do not participate in equality according to the chosen contract, and tests reflect that decision.

## 8. Expanding to Property-Based Testing

Property-based testing generates many inputs and verifies contract laws rather than checking only a handful of fixed examples. To be effective, the generator must actively produce challenging structures:

1. Generate a base value and then create independent equal instances from it.
2. Generate variants that differ by only one significant field at a time.
3. Increase the probability of boundary values: `MIN_VALUE`, `MAX_VALUE`, `-1`, `0`, `1`, empty strings, and large lengths if the domain allows them.
4. Generate pairs that tie on the primary criterion but differ on the comparator's secondary criterion.
5. Include `null` only when the policy permits it; otherwise, test the rejected domain with dedicated exception test cases.
6. When inheritance relationships are supported, generate both superclass and subclass instances to verify symmetry and transitivity across them.

Three purely random objects are almost never equal, so uniform random generation can easily miss `equals` bugs. You need a generator of equivalence groups, not just a generator of isolated values.

Record the failing seed or input set and shrink it down to a minimal pair or triple. Failure messages should include the objects, relevant fields, and comparison result signs. After fixing the bug, keep that minimal case as a deterministic regression test. Do not rely on hard-to-reproduce changing random data as your only proof.

When integrating with JUnit, separate each law group into its own test or parameterized test so failures pinpoint the exact property that broke. Apply these verification helpers to the application's real domain classes and comparators; testing only an illustrative record does not validate other classes in the system.

## 9. Tests That Can PASS Yet Still Miss Bugs

| Incomplete Test Approach | Missed Issue | How to Fix |
| --- | --- | --- |
| Only calling `a.equals(a)` | Reference-identity equality passes even when value equality is required | Two independent instances with the same value plus single-field variants |
| Only testing unequal pairs | Equal-hash law and transitivity may never be triggered | Equivalence group of three distinct equal instances |
| Requiring unequal values to have different hashes | Rejects valid hash collisions | Only assert `equals` implies equal hash; add collision test cases via collections |
| Only sorting a single list and checking for no errors | Many broken comparators go undetected on that specific input | Verify pairwise/triple laws and explicit domain ordering |
| Comparing `compare` result against exact `-1` or `1` | Imposes a requirement stricter than the contract | Compare signs (`Integer.signum`) |
| Only using small numbers | Subtraction overflow bugs remain hidden | Boundary extremes and pairs spanning opposite sides of the numeric range |
| Assuming a law-abiding comparator works for every `TreeSet` | Ignores `compare == 0` groups that differ from `equals` groups | Check consistency with `equals` and verify `Set` size/lookups |
| Comparing two comparators via `equals` to infer identical sorting | Equivalent comparators are not required to be `equals` | Compare ordering relationships across sample inputs when that is the test goal |

A comparator that violates the contract might be caught by a sorting algorithm throwing an error, but the absence of an exception does not prove the comparator is valid. The API contract treats violation detection during sorting as best-effort. [Arrays.sort documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html).

## 10. Practical Exercise

A `Student` class has `studentId`, `displayName`, and `score`. Equality is defined by `studentId`, while the UI needs to display students ordered by descending score and then by name.

1. Write a fixture group that separates the `equals`/`hashCode` laws from the domain meaning of "same student." If only the name or score changes while the ID remains the same, what relationship must hold for `equals` and `hashCode`?
2. Verify the display comparator against both the comparator laws and the expected domain order, including tied scores and tied names.
3. Two records representing the same student with different scores can be distinguished by the display comparator. Is that comparator consistent with `equals`?
4. If you need a `Set` keyed by student identity, should you pass the display comparator directly to a `TreeSet`? Determine the appropriate data structure or ordering relationship before writing your assertions.
5. Add boundary cases, `null` policy checks, and regression test cases for any bugs discovered.

A good test suite makes it clear why two objects are equal or why one object must come before another. Contract laws catch structural bugs; domain fixtures preserve the exact meaning the application requires.
