# Triple Testing for `compareTo()` and `Comparator`

## Goal and Scope

A comparison that looks right when testing two values in isolation can still **fail when considering three values**. This lesson guides you through verifying the ordering contract of `Comparable.compareTo()` and `Comparator.compare()` in Java: sign reversal when swapping operands, transitivity, and consistency of values considered equal in ordering. The focus is on constructing and testing **triples `(a, b, c)`**, finding counterexamples, and fixing the comparator so sorting, `TreeSet`, and `TreeMap` behave predictably.

The tests here verify the **ordering contract**, not replacing `equals()`/`hashCode()` tests; nevertheless, you must understand the relationship between `compare(x, y) == 0` and `equals()` when using sorted sets or maps.

## 1. Interpreting Comparison Results Properly

For two objects `x`, `y`:

- `x.compareTo(y) < 0` or `comparator.compare(x, y) < 0`: `x` comes before `y`.
- Result equal to `0`: `x` and `y` are **equivalent under the ordering** being evaluated.
- Result `> 0`: `x` comes after `y`.

The contract **only specifies the sign**, not requiring exact values `-1`, `0`, or `1`. Therefore, tests should normalize with `Integer.signum(result)`, avoiding `compare(x, y) == -1` or negating the raw result (which can overflow when the result is `Integer.MIN_VALUE`).

`Comparable<T>` defines the **natural ordering** of a type via `compareTo(T other)`. `Comparator<T>` allows defining an ordering external to the object, such as sorting `Person` by age, then by code. Both mechanisms share the essential verification rules below. A `Comparator` may accept `null` if it explicitly defines how to handle it; calling `compareTo(null)` on a non-`null` object must throw `NullPointerException` per the `Comparable` contract.

Notation used in this lesson: `c(x,y)` is the result of `x.compareTo(y)` or `comparator.compare(x,y)`; `sgn(v)` is the sign of integer `v`.

## 2. Three Groups of Conditions to Verify

### 2.1. Swapping Operands: Pair `(a, b)`

For all elements in the valid comparison domain:

```text
sgn(c(a,b)) == -sgn(c(b,a))
c(a,a) == 0
```

If `a < b`, then the reversed direction must be `b > a`. If `a` and `b` are considered to occupy the same rank (`c(a,b)==0`), then the reversed direction also equals `0`. Checking `c(a,a)==0` is a simple check complementing antisymmetry of signs.

**Common mistake:** using `return a - b;` on integers; subtraction can overflow and cause both directions to be negative. Use `Integer.compare(a,b)`, `Long.compare(a,b)`, or `Comparator.comparingInt(...)` depending on context.

### 2.2. Transitivity: Triple `(a, b, c)`

If `a > b` and `b > c`, then `a > c` must hold; similarly for the less-than direction:

```text
c(a,b) > 0  &&  c(b,c) > 0   =>   c(a,c) > 0
c(a,b) < 0  &&  c(b,c) < 0   =>   c(a,c) < 0
```

This is why **triple testing** is needed: testing each pair individually does not catch a contradictory cycle.

For example, a custom comparator describes the cycle `0 < 1`, `1 < 2`, yet `2 < 0`. Each pair has a clear before/after direction and proper opposite signs. However, the triple `(0,1,2)` proves it wrong: from `0 < 1` and `1 < 2` it must follow that `0 < 2`, contradicting the result `0 > 2`. Such a comparator does not produce a consistent ordering.

### 2.3. Zero Equivalence Must Be Consistent With a Third Element

If `a` and `b` are considered order-equivalent, then relative to **any `c`** they must share the same before/after/tied relationship:

```text
c(a,b) == 0  =>  sgn(c(a,c)) == sgn(c(b,c))
```

Combined with the operand-swapping rule, this relation also holds when the third element is on the left side. It guarantees that tied groups (`compare == 0`) behave as valid equivalence classes; for instance, if `a ~ b` and `b ~ c`, then `a ~ c`.

Counterexample: a comparator treats `0` and `2` as equal, while comparing other pairs by integer order. Examining `(a,b,c)=(0,2,1)`, we get `c(0,2)==0`, yet `c(0,1)<0` while `c(2,1)>0`. This equivalence class is inconsistent. Testing transitivity only on pairs where **comparison is non-zero** is insufficient to cover the entire contract.

## 3. Writing a Standalone Verifier in Java 17+

The complete example below iterates over all pairs and triples on a small sample set. It uses the **same verification function** for both `compareTo()` (passing a method reference) and `Comparator`. Four scenarios demonstrate two valid orderings and two intentionally broken orderings.

```java
// OrderingTriplesDemo.java
import java.util.Comparator;
import java.util.List;

public final class OrderingTriplesDemo {
    private static int sign(int value) {
        return Integer.signum(value);
    }

    private static <T> void checkContract(
            List<T> samples, Comparator<? super T> comparator) {

        // Check reflexivity and opposite signs on all pairs.
        for (T a : samples) {
            if (sign(comparator.compare(a, a)) != 0) {
                throw new AssertionError("reflexivity");
            }
            for (T b : samples) {
                int ab = sign(comparator.compare(a, b));
                int ba = sign(comparator.compare(b, a));
                if (ab != -ba) {
                    throw new AssertionError("opposite signs");
                }
            }
        }

        // Check all ordered triples (a, b, c).
        for (T a : samples) {
            for (T b : samples) {
                for (T c : samples) {
                    int ab = sign(comparator.compare(a, b));
                    int bc = sign(comparator.compare(b, c));
                    int ac = sign(comparator.compare(a, c));

                    if (ab == 0 &&
                            ac != sign(comparator.compare(b, c))) {
                        throw new AssertionError("zero-class consistency");
                    }
                    if ((ab > 0 && bc > 0 && ac <= 0) ||
                            (ab < 0 && bc < 0 && ac >= 0)) {
                        throw new AssertionError("transitivity");
                    }
                }
            }
        }
    }

    private static void run(
            String label, List<Integer> samples,
            Comparator<Integer> comparator) {
        try {
            checkContract(samples, comparator);
            System.out.println(label + ": PASS");
        } catch (AssertionError error) {
            System.out.println(label + ": FAIL - " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        Comparator<Integer> byAbsoluteValue =
                Comparator.comparingLong(x -> Math.abs((long) x));

        // Counterexample 1: 0 < 1 < 2 < 0, violates transitivity.
        Comparator<Integer> cyclic = (a, b) -> {
            if (a.equals(b)) {
                return 0;
            }
            return (a + 1) % 3 == b ? -1 : 1;
        };

        // Counterexample 2: treats 0 ~ 2 while comparing other pairs numerically.
        Comparator<Integer> merged = (a, b) -> {
            if ((a == 0 && b == 2) || (a == 2 && b == 0)) {
                return 0;
            }
            return Integer.compare(a, b);
        };

        run("Integer.compareTo", List.of(-2, -1, 0, 1, 2),
                Integer::compareTo);
        run("Comparator abs", List.of(-2, -1, 0, 1, 2),
                byAbsoluteValue);
        run("Comparator cycle", List.of(0, 1, 2), cyclic);
        run("Comparator merged", List.of(0, 2, 1), merged);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 OrderingTriplesDemo.java
java OrderingTriplesDemo
```

Exact output:

```text
Integer.compareTo: PASS
Comparator abs: PASS
Comparator cycle: FAIL - transitivity
Comparator merged: FAIL - zero-class consistency
```

**How to read the output:**

- `Integer::compareTo` uses natural ordering, so it passes the test samples.
- Comparing by absolute value creates groups `-2 ~ 2`, `-1 ~ 1`. This is still a valid ordering: elements tied by absolute value have the exact same relationship to every third element. Tied groups **do not force** objects to be `equals()`.
- `cyclic` preserves opposite signs for every pair yet forms a comparison cycle.
- `merged` improperly treats `0` and `2` as tied; choosing the sample order `[0,2,1]` causes the verifier to report the `zero-class consistency` counterexample before other violation forms.

The `cyclic` and `merged` comparators are **for demonstrating bugs only**, not for sorting real data. `checkContract` checks a finite set of samples, so `PASS` does not prove correctness for all possible values; both reasoning about the ordering logic and a representative test set are needed.

## 4. Distinguishing Consistency With `equals()`

The contract above does not require `compare(a,b)==0` to always imply `a.equals(b)`: that is a very strong recommendation of `Comparable` and something to examine for `Comparator`, **not a mandatory requirement in every ordering design**. A comparator by string length, by age, or by absolute value can be valid while still grouping multiple `equals()`-distinct objects into the same position.

However, `TreeSet` and `TreeMap` use the **result of the comparator or `compareTo` to determine duplicate keys/elements**. Therefore, when a comparator returns 0 for two different objects, the collection may retain a single element or entry for both keys. This is not a bug in the collection, but a consequence of the chosen ordering.

Java 17+ example:

```java
// TreeSetOrderingDemo.java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetOrderingDemo {
    record Member(int age, String code) {}

    public static void main(String[] args) {
        Member a = new Member(30, "A");
        Member b = new Member(30, "B");

        Comparator<Member> byAge =
                Comparator.comparingInt(Member::age);
        Set<Member> onlyAge = new TreeSet<>(byAge);
        onlyAge.add(a);
        onlyAge.add(b);

        Comparator<Member> byAgeThenCode = byAge
                .thenComparing(Member::code);
        Set<Member> ageAndCode = new TreeSet<>(byAgeThenCode);
        ageAndCode.add(a);
        ageAndCode.add(b);

        System.out.println(a.equals(b));
        System.out.println(onlyAge.size());
        System.out.println(ageAndCode.size());
    }
}
```

```bash
javac TreeSetOrderingDemo.java
java TreeSetOrderingDemo
```

```text
false
1
2
```

`record Member` has an `equals()` checking both age and code. The age-only comparator treats the two elements as tied; the comparator with `thenComparing(Member::code)` adds a distinguishing tie-breaker criterion. You must select keys and secondary criteria according to business requirements: sometimes intentionally merging multiple elements is right, provided you clearly understand the impact on sorted structures.

## 5. Choosing Triples for Valuable Testing

A test dataset should include **multiple equivalence classes, boundary points, and values prone to contradictions**. Choose not just strictly increasing sequences `(1,2,3)` but also triples containing one or more `compare==0` pairs.

| Sample group | Example | Issue to catch |
| --- | --- | --- |
| Three distinct elements | `(a,b,c)` with `a<b<c` and all permutations | Transitivity in both directions, comparison cycles |
| Two tied elements | `compare(a,b)==0` while `a` and `b` are different objects | Relationship with `c` must be identical |
| Three tied elements | `a~b`, `b~c` | Transitivity of the tied equivalence class |
| Integer boundaries | `Integer.MIN_VALUE`, `-1`, `0`, `Integer.MAX_VALUE` | Overflow on subtraction, negating `MIN_VALUE` |
| Multiple sort keys | Same score, different age/code; or same primary and secondary key | `thenComparing`, tie-breaking |
| Strings, upper/lower case | `"a"`, `"A"`, empty string, accented characters | Normalization, locale, transitive comparison |
| `null` (if comparator supports it) | `(null,a,b)` | Consistent `nullsFirst`/`nullsLast` policy |
| Floating-point | `-0.0`, `+0.0`, `NaN`, infinities | Semantics of `Double.compare` differ from standard `<`/`>` operators |

When testing `Comparable`, only construct triples from objects that are actually mutually comparable under the type's contract. When testing a comparator that may throw an exception by design on certain inputs, cleanly separate valid input groups from cases expected to throw. Never "fix" a test by swallowing all exceptions and marking it PASS.

### Practical Workflow

1. **Define the valid domain and tie policy:** which fields are compared, whether `null` is allowed, and whether the comparator may group objects that are not `equals()`.
2. **Test each pair:** `c(a,a)==0`; both directions have opposite signs. Use `signum`, not exact return values.
3. **Test all ordered triples:** both transitivity directions and the `c(a,b)==0` case. Do not test only one ordering `(a,b,c)`: permuting positions can reveal new bugs.
4. **Preserve a minimal counterexample triple:** record the three input values, the signs of `c(a,b)`, `c(b,c)`, `c(a,c)`, and why it failed. This helps fix the comparison condition accurately.
5. **Add regression tests:** whenever adding a field to `compareTo`, changing a comparator, or changing the `null` policy, re-run tests against boundary samples and previously failing cases.

With `n` sample elements, checking all pairs takes about `O(n²)` checks, and all triples take `O(n³)` iterations. This is well suited to running exhaustively on a **small curated sample set**. For large domains, you can generate many random triples with a fixed seed and use property-based testing; upon failure, shrink to an understandable triple. Random generation is a supplement, not a replacement for boundary samples or correctness reasoning.

## 6. Ways of Writing a Comparator That Easily Break the Contract

### Using Subtraction Instead of `Integer.compare`

```java
// Wrong on int overflow:
Comparator<Integer> unsafe = (a, b) -> a - b;

// Safe across the entire int range:
Comparator<Integer> safe = Integer::compare;
```

With `a = Integer.MAX_VALUE`, `b = -1`, both `a-b` and `b-a` can yield `Integer.MIN_VALUE` due to overflow; both directions turn negative, violating opposite signs. Do not use `Math.abs(a-b)` or negate `-compare(b,a)` directly to determine the expected sign.

### Chaining Priority Rules That Form a Cycle

Conditional logic like "A takes precedence over B, B takes precedence over C, C takes precedence over A" can satisfy every pairwise test and still break transitivity. If the business priority is genuinely cyclic, it is **unsuitable as a Comparator** for a total order. Model scheduling/priority rules as a separate relation, or pick a key with a total order for sorting.

### Arbitrarily Returning 0 for "Don't Know How to Compare"

`0` must signify equal rank under a consistent ordering relation, **not skipping the comparison**. If you occasionally return 0 for two values just to "avoid handling them", triples involving a third element can contradict each other. Define a valid secondary criterion or an explicit policy for incomparable inputs.

### Depending on Time-Varying State

If a comparator reads `System.currentTimeMillis()`, `Random`, mutable data, or a mutable field modified while the element sits in a `TreeSet`/`TreeMap`, two comparisons of the same pair can yield different results. Triple checks assume **a stable comparison state**. Sort by immutable keys, take a snapshot, or rebuild the collection when order-affecting keys have changed.

### Missing Tie-Breakers or Special-Type Handling

For multi-key sorting, use `Comparator.comparing(...).thenComparing(...)` to build an ordering out of valid comparisons. For floating-point numbers, use `Double.compare` or `comparingDouble` and explicitly test `NaN`/`±0.0`; do not improvise solely from boolean expressions `a < b`, `a > b`. For internationalized strings, if using `Collator`, keep locale, normalization rules, and configuration uniform throughout comparison.

## 7. Putting the Verifier into Unit Tests

The `checkContract` function in the example can be placed in a test utility and invoked in a test case with a fixed sample set. With JUnit, simply let `AssertionError` propagate; the test runner will report FAIL. Include **at least one triple known to fail** for each kind of broken comparator fixed, to avoid testing only easy scenarios.

You can also check additional properties on realistic data:

- Repeated comparison results on the same pair do not change while keys remain unchanged.
- After sorting, every adjacent pair is non-decreasing under the comparator; still run triple checks because output that "looks sorted" does not prove the comparator is valid.
- If the application requires `compare(a,b)==0` to match `a.equals(b)`, test **this additional business condition** separately. A contract-valid comparator can still intentionally be inconsistent with `equals()`.

When a triple fails, fix the comparison algorithm itself: key comparison rules, tie-breaker, `null` handling, overflow, or mutable data source. Changing the sample iteration order to make the test "green" does not solve the bug.

## 8. Self-Check Checklist

- If `compare(a,b)=42`, is that valid? **Yes**, as long as the sign and all contract conditions hold; it does not need to be `1`.
- If `a<b`, `b<c`, yet `a>c`, what is violated? **Transitivity**, which requires triples to detect.
- If `compare(a,b)==0`, must `a.equals(b)` hold? **Not in every case**, though both elements' comparisons against any `c` must share the same sign; `TreeSet`/`TreeMap` treat them as the same key under the ordering.
- Why use `Integer.signum`? To verify the **sign**, avoiding assumptions of `±1` values and avoiding overflow when negating raw integers.
- Why is `PASS` on 5 elements insufficient to conclude a comparator is always right? All triples were only checked within the **set of 5 samples**; bugs may appear at boundary values or untested data classes.

**Remember:** to trust a `compareTo()` or `Comparator`, test both **reversed pairs** and **all representative triples**, especially triples containing two elements with `compare == 0`. Plausible-looking sorted output on a few examples is not enough to prove the ordering contract.

## References

- [Java SE 17 — Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
