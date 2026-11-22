# Transitivity of Ordering Relations in Java

## 1. What does transitivity mean?

When objects have a **natural ordering** via `Comparable<T>.compareTo(T)`, the order must follow consistent rules. One of the most important requirements is **transitivity**:

> If `a` comes after `b` and `b` comes after `c`, then `a` must also come after `c`.

In terms of `compareTo` results, this is expressed by signs:

~~~text
a.compareTo(b) > 0
b.compareTo(c) > 0
----------------
a.compareTo(c) > 0
~~~

Similarly, if `a.compareTo(b) < 0` and `b.compareTo(c) < 0`, then `a.compareTo(c) < 0`. Here **negative** means comes before, **0** means equivalent in ordering, and **positive** means comes after; Java does not require results to equal `-1` or `1`.

For example, if three scores have the relationship `70 < 80 < 90`, the program must not have a comparison rule that makes `90 < 70`. If that happens, the three values cannot be arranged into a consistent linear order.

Transitivity must hold for **every valid triple of objects**, not just in a few test datasets. It is vital for sorting, binary search, and ordered sets/maps like `TreeSet` and `TreeMap`.

## 2. What else does the compareTo contract require?

To define a proper natural ordering, checking transitivity alone is not enough. According to the `Comparable` contract, the following rules must also be considered.

| Requirement | Interpretation | Example |
| --- | --- | --- |
| Sign reversal | `sgn(x.compareTo(y)) == -sgn(y.compareTo(x))` | If x comes after y then y comes before x |
| Transitivity | If `x > y` and `y > z` then `x > z` | 90 > 80 > 70 ⇒ 90 > 70 |
| Ordering-equivalent objects | If `x.compareTo(y) == 0` then for all z, `sgn(x.compareTo(z)) == sgn(y.compareTo(z))` | Two tied values must have the same before/after relation with every other value |
| Consistency with `equals` | Should have `x.compareTo(y) == 0` if and only if `x.equals(y)` | Ordered collections handle duplicate keys based on `compareTo` |

The `sgn` notation indicates the **sign** of an integer: negative becomes `-1`, zero becomes `0`, positive becomes `1`. The sign-reversal condition implies `x.compareTo(x)` must equal `0`.

**Consistency with `equals`** is strongly recommended though not mandatory in every `Comparable` class. A famous example is `BigDecimal`: `new BigDecimal("4.0").compareTo(new BigDecimal("4.00")) == 0`, while `equals` returns `false` because the scale representations differ. This does not violate transitivity; it shows that **equivalence in ordering** and **equality by `equals`** are two relations that can differ.

The condition "equal to 0 implies same relation to every z" is especially critical: if one object is considered tied with a second object yet sits on the opposite side of a third object, sorting algorithms will receive contradictory results.

## 3. Building a valid natural ordering with comparison keys

Suppose an exam result has two attributes:

- `score`: points, ascending.
- `candidate`: name, used to break ties in score lexicographically.

A clear ordering is **compare score first; only if scores are equal, compare name**. This is lexicographical comparison on the key pair `(score, candidate)`. When each component uses a consistent ordering relation, comparing in a fixed priority order also preserves transitivity.

Some helpful rules:

1. Choose the fields defining the order and **the priority order of those fields** from the start.
2. Use `Integer.compare`, `Long.compare`, `String.compareTo`, or `Comparator.comparing(...).thenComparing(...)` instead of computing signs via subtraction prone to overflow.
3. If the primary key differs, return the primary key's result immediately; only inspect secondary keys when the primary key is equal.
4. Ensure fields involved in comparison remain stable while the object is inside a `TreeSet` or serving as a `TreeMap` key.
5. Clearly decide whether `null` is valid. If a field can be `null`, apply a consistent `nullsFirst` or `nullsLast` rule, or validate non-`null` at construction.

## 4. Runnable Java 17 example

The program includes an `ExamResult` class with a transitive natural ordering, a cyclic comparator illustrating a contract violation, and an incorrect comparison using subtraction that risks `int` overflow.

Save to file **TransitiveOrderDemo.java**:

~~~java
import java.util.Comparator;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class TransitiveOrderDemo {
    static final class ExamResult implements Comparable<ExamResult> {
        private final int score;
        private final String candidate;

        ExamResult(int score, String candidate) {
            this.score = score;
            this.candidate = Objects.requireNonNull(candidate, "candidate");
        }

        @Override
        public int compareTo(ExamResult other) {
            int byScore = Integer.compare(score, other.score);
            if (byScore != 0) {
                return byScore;
            }
            return candidate.compareTo(other.candidate);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof ExamResult that
                            && score == that.score
                            && candidate.equals(that.candidate));
        }

        @Override
        public int hashCode() {
            return Objects.hash(score, candidate);
        }

        @Override
        public String toString() {
            return candidate + ":" + score;
        }
    }

    enum Move { ROCK, PAPER, SCISSORS }

    static final Comparator<Move> CYCLIC = (left, right) -> {
        if (left == right) {
            return 0;
        }
        boolean leftWins =
                (left == Move.ROCK && right == Move.SCISSORS)
                || (left == Move.SCISSORS && right == Move.PAPER)
                || (left == Move.PAPER && right == Move.ROCK);
        return leftWins ? 1 : -1;
    };

    public static void main(String[] args) {
        ExamResult a = new ExamResult(70, "An");
        ExamResult b = new ExamResult(80, "Binh");
        ExamResult c = new ExamResult(90, "Chi");

        System.out.println("a < b: " + (a.compareTo(b) < 0));
        System.out.println("b < c: " + (b.compareTo(c) < 0));
        System.out.println("a < c: " + (a.compareTo(c) < 0));

        ExamResult tiedA = new ExamResult(80, "An");
        System.out.println("tie by name: "
                + (tiedA.compareTo(b) < 0));
        System.out.println("zero agrees with equals: "
                + (b.compareTo(new ExamResult(80, "Binh")) == 0
                        && b.equals(new ExamResult(80, "Binh"))));

        Set<ExamResult> results = new TreeSet<>();
        results.add(c);
        results.add(a);
        results.add(b);
        results.add(new ExamResult(80, "Binh"));
        System.out.println("TreeSet: " + results);

        System.out.println("rock > scissors: "
                + (CYCLIC.compare(Move.ROCK, Move.SCISSORS) > 0));
        System.out.println("scissors > paper: "
                + (CYCLIC.compare(Move.SCISSORS, Move.PAPER) > 0));
        System.out.println("rock > paper: "
                + (CYCLIC.compare(Move.ROCK, Move.PAPER) > 0));

        int high = Integer.MAX_VALUE;
        int middle = 0;
        int low = -1;
        System.out.println("subtract high > middle: "
                + (high - middle > 0));
        System.out.println("subtract middle > low: "
                + (middle - low > 0));
        System.out.println("subtract high > low: "
                + (high - low > 0));
        System.out.println("Integer.compare high > low: "
                + (Integer.compare(high, low) > 0));
    }
}
~~~

Compile/run on JDK 17 or newer:

~~~bash
javac TransitiveOrderDemo.java
java TransitiveOrderDemo
~~~

Standard output:

~~~text
a < b: true
b < c: true
a < c: true
tie by name: true
zero agrees with equals: true
TreeSet: [An:70, Binh:80, Chi:90]
rock > scissors: true
scissors > paper: true
rock > paper: false
subtract high > middle: true
subtract middle > low: true
subtract high > low: false
Integer.compare high > low: true
~~~

### Explanation

- The three `ExamResult` objects have scores `70 < 80 < 90`, so `a < b`, `b < c`, and `a < c` are all true. The results follow transitivity.
- When scores are both `80`, the program uses the name as the secondary key. `"An"` comes before `"Binh"`, so tie-breaking does not conflict with the score relation.
- `TreeSet` uses `compareTo` to sort and determine duplicates by ordering. The duplicate `ExamResult(80, "Binh")` does not add a new element; iteration output is displayed in ascending order.
- `ExamResult` is `final`, and the compared fields are `final`; `equals` and `hashCode` use the exact pair `(score, candidate)`, so all contracts align with each other.
- `CYCLIC` considers ROCK after SCISSORS, SCISSORS after PAPER, yet PAPER after ROCK. It expresses rock–paper–scissors game logic, **not a linear ordering relation**. The first two comparisons are `true` yet the transitive conclusion is `false`.
- The subtraction `high - low` overflows `int` because `Integer.MAX_VALUE - (-1)` exceeds the integer limit. The sign flips, creating the triple `high > middle > low` where subtraction reports `high` is not greater than `low`. `Integer.compare` handles this case properly.

The example intentionally **does not pass the cyclic comparator into `TreeSet`**: when the contract is violated, sorting/search results cease to be trustworthy. Seeing no error or exception in a single run does not prove a comparator is valid.

## 5. Why can't the "rock–paper–scissors" rule be a natural ordering?

The "beats" relation in rock–paper–scissors has a cycle:

~~~text
ROCK > SCISSORS
SCISSORS > PAPER
PAPER > ROCK
~~~

If we try to interpret `>` as "comes after in natural ordering", the first two lines force `ROCK > PAPER`. Yet the final line states `PAPER > ROCK`. Therefore this relation is **non-transitive** and cannot be used as a contract-compliant natural ordering.

A business relation can be logical while **not being an ordering relation**. If you want to represent "which opponent wins", use a method such as `beats(other)` returning `boolean` or a dedicated outcome type. Only create a `Comparator` when there is genuinely a consistent ordering that sorting algorithms can use.

If you want to display the three choices in a fixed order, you can sort by a predefined code/rank (for example ROCK, PAPER, SCISSORS). That display order differs from the relation of who beats whom.

## 6. Impact of violating transitivity

### 6.1. Sorting

`Arrays.sort`, `List.sort`, and `Collections.sort` rely on a comparator or `compareTo` representing a consistent ordering. A non-transitive comparator can make results unpredictable or cause the sorting algorithm to detect the violation and throw `IllegalArgumentException` in some cases. **Do not expect the JVM to always throw an exception**: sometimes small datasets still get sorted and look right, yet there is no guarantee of valid ordering for a broken comparator.

### 6.2. TreeSet and TreeMap

`TreeSet` and `TreeMap` use the ordering relation to organize, search, and determine keys considered equivalent. Violating the contract can cause `contains`, `get`, `remove`, or ordered traversal to yield unexpected results. These collections assume comparison results are stable and consistent enough to locate a position in the tree.

In particular, `TreeSet`/`TreeMap` treat **`compare(a, b) == 0`** or **`a.compareTo(b) == 0`** as the equivalence relation when identifying duplicate elements/keys. If this relation does not match `equals`, the collection still operates by the comparison rule yet violates expectations of the general `Set`/`Map` contract. Therefore, ensure consistency with `equals` or explicitly document intentional divergence.

### 6.3. Binary search

Binary search requires the sequence to be sorted according to the exact same comparison rule used during lookup. A non-transitive comparator undermines halving the search range: you cannot rely on elements to the left or right having a consistent relation with the target key.

You cannot fix a broken relation by arbitrarily flipping signs or repeating comparisons multiple times. You must fix **the ordering definition**.

## 7. Error-prone ways to write compareTo

### 7.1. Subtracting two integer values directly

~~~java
@Override
public int compareTo(Score other) {
    return score - other.score; // Can overflow int
}
~~~

This is an **illustrative buggy snippet in a hypothetical Score class**, not a standalone program. If the difference overflows `int`, the result sign can be wrong, leading to violations of sign reversal or transitivity. Replace with:

~~~java
@Override
public int compareTo(Score other) {
    return Integer.compare(score, other.score);
}
~~~

For `long`, likewise use `Long.compare` instead of casting the difference to `int`. Do not write a comparator that merely returns `0` whenever two numbers share the same sign, because that causes distinct values to be treated as tied and conflicts with the chosen equality policy.

### 7.2. Comparing with time-varying data

A `compareTo` method that reads a clock, calls an external service, or relies on a field modified while the element is already in a `TreeSet` can return different results for the same pair of objects. This is a **consistency across comparisons** issue that can break tree lookup assumptions even if the formula looks transitive at any single instant.

Prefer stable ranking keys. If the order must change, remove the item from the collection while it is still identifiable under its old state, update the data, and re-insert it under the new state; in multithreaded applications, coordinate synchronization across the entire operation.

### 7.3. Switching field priority order based on conditions

For example, comparing `a` and `b` prioritizes score, while comparing `b` and `c` prioritizes name because of an object-dependent business flag. If choosing the priority field depends **on the pair being compared**, rather than a globally consistent priority order, a cycle `a < b < c < a` can arise.

The usual solution is choosing a fixed key tuple, such as `(priority, createdAt, id)`, and comparing left to right. Adding a final `id` key can also break ties when a **deterministic total order** is needed, though you must clearly define which keys belong to ordering equality.

### 7.4. Forgetting the null policy

By `Comparable`, `compareTo(null)` normally throws `NullPointerException`, even when `equals(null)` returns `false`. If an **internal field** can be `null`, you must choose an explicit handling strategy in the comparator, for example:

~~~java
Comparator<String> nullableNames =
        Comparator.nullsLast(String::compareTo);
~~~

This is a **comparator declaration snippet**, not a standalone program. It places `null` after non-`null` strings. Apply this policy consistently throughout the entire sorting rule; do not arbitrarily treat `null` as smaller in one branch and larger in another.

## 8. Checking transitivity when writing or editing a Comparable class

A small test suite should verify both typical cases and boundaries:

1. **Sign reversal:** for pairs `a, b`, the sign of `a.compareTo(b)` must be the opposite of `b.compareTo(a)`. Also check `a.compareTo(a) == 0`.
2. **Ascending and descending transitivity:** for all sample triples with `a < b < c`, check `a < c`; and for `a > b > c`, check `a > c`.
3. **Tied cases:** if `a.compareTo(b) == 0`, both objects must have the same comparison sign against every sample `c`.
4. **Multiple keys:** create pairs with equal primary keys but different secondary keys, and pairs with different primary keys. Ensure tie-breaking operates in a fixed priority order.
5. **Boundary values:** negative numbers, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, empty strings, `null` if attributes allow it.
6. **Consistency with equals:** verify whether `compareTo == 0` aligns with `equals` as designed. If intentionally different, document the reason and impact on `TreeSet`/`TreeMap`.
7. **Stability:** identical unmodified objects must yield the same result sign across multiple comparisons.

A test helper function can be written inside the test class:

~~~java
static <T extends Comparable<? super T>> boolean transitiveLess(
        T a, T b, T c) {
    return !(a.compareTo(b) < 0 && b.compareTo(c) < 0)
            || a.compareTo(c) < 0;
}
~~~

This is an **illustrative test method**, not a standalone program. If the premise `a < b` and `b < c` does not hold simultaneously, this implication check returns `true` because there is no violation for that triple. For strong verification, generate many triples covering both satisfied premises and reversed orders. Property-based testing can help generate random data and boundary values, yet does not replace designing a valid ordering relation from the start.

**Remember:** In Java, an ordering relation used by `Comparable` or `Comparator` must be **transitive**: if `a > b` and `b > c` then `a > c`. Choose comparison keys with a stable priority order, use overflow-safe `compare` functions, and never feed cyclic relations into sorting algorithms or ordered collections.