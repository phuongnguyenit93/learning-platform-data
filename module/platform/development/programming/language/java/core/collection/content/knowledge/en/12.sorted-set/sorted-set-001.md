# SortedSet and Natural Ordering or Comparator

## 1. A Set That Both Deduplicates and Maintains Order

Suppose a program receives the priority levels `7, 2, 9, 2, 5`. You need each level to appear once and always be traversed in ascending order. If you only put the data into an arbitrary set, the deduplication requirement does not guarantee the ordering requirement. If you only sort a list, the two occurrences of the number 2 may still remain.

`SortedSet<E>` represents a set that has an ordering rule over its elements. A common implementation is `TreeSet<E>`. With the natural ordering of `Integer`, the example above produces `[2, 5, 7, 9]`, regardless of whether 7 was added before 2.

Even more important than "the printed output is sorted" is that **the comparison rule also decides which elements are considered duplicates**. If comparing two objects yields 0, the sorted set treats them as occupying the same equivalence position. Choosing a `Comparator` is therefore choosing both the sequence and part of the meaning of uniqueness.

This lesson progresses from the two sources of ordering — natural ordering and `Comparator` — to custom object examples, secondary criteria, equality cases, basic methods, and pitfalls to avoid. The complete code uses APIs available in Java 17.

You only need to know variables, classes, methods, generic types such as `List<Integer>`, and loops. The concepts of `Comparable`, `Comparator`, and comparison return values are explained before use.

## 2. SortedSet Is the Contract; TreeSet Is One Implementation

You can read the declaration:

~~~java
SortedSet<Integer> priorities = new TreeSet<>();
~~~

as follows:

- `SortedSet<Integer>` is the type visible to the calling code: an ordered set of integers and ordering-related operations.
- `new TreeSet<>()` creates the concrete object implementing that contract.
- `Integer` is the element type; `int` is boxed into `Integer` when needed.

The snippet above is an illustrative declaration; you need to import `java.util.SortedSet` and `java.util.TreeSet` when placing it in a program.

`SortedSet` extends `Set`, so it still has `add`, `contains`, `remove`, `size`, and iteration capability. It adds ways to retrieve the first/last elements, query the comparison rule, and create ordered range views.

Conceptual picture:

~~~text
Set
  └─ SortedSet: adds the ordering contract
       └─ NavigableSet: adds ordered neighbor-lookup operations
            └─ TreeSet: a concrete implementation class
~~~

The diagram describes type relationships, not the node structure of the tree in memory. Neighbor-lookup operations such as `floor` or `ceiling` belong to the extended scope; to understand natural ordering and `Comparator`, you first need to grasp the `SortedSet` contract properly.

According to the API, the order can come from the elements themselves or from a `Comparator` provided when creating the set. Iteration proceeds in ascending order **of the active rule**. "Ascending" here does not automatically mean smallest number to largest number in every set. [Java 17: SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html).

## 3. Natural Ordering Comes from Comparable

Natural ordering is the comparison rule that an element type provides via `Comparable<T>`, with the method:

~~~java
int compareTo(T other);
~~~

This is a condensed signature for reading its meaning, not a standalone program.

For `a.compareTo(b)`:

| Result | Meaning according to the type's rule |
| --- | --- |
| Less than 0 | `a` comes before `b` |
| Equal to 0 | `a` and `b` are equivalent in order |
| Greater than 0 | `a` comes after `b` |

Only the negative, 0, or positive sign carries general meaning. Do not write code that only accepts `-1` and `1`, because a valid comparison may return a different negative or positive number.

For example, the natural ordering of `Integer` is numerical order. `new TreeSet<Integer>()` does not require you to pass an extra function to know that 2 comes before 7.

For `String`, natural ordering is lexicographical order based on the values of the character code units in the string. It does not automatically become a Vietnamese name sorting rule, does not automatically ignore case, and does not interpret version strings as numeric components. For instance, sorting the strings `"1.10"` and `"1.9"` is not equivalent to comparing the two number pairs `(1, 10)` and `(1, 9)`. [Java 17: String.compareTo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#compareTo(java.lang.String)).

A class does not automatically have a natural ordering just because it has numeric fields or `toString`. A `record` does not automatically implement `Comparable` either. If you want `Version` to have a natural ordering, you must declare it and write an appropriate comparison rule.

The example in the program below compares versions by major part first, then minor part:

~~~text
1.9  comes before  1.10  comes before  2.0
~~~

That is a design decision for the `Version` model in this lesson; it does not attempt to interpret every real-world software versioning convention.

## 4. Comparator Is an Externally Provided Ordering Rule

A data type may need multiple ways of presentation. A candidate list might prioritize high scores; another screen might prioritize names. You should not force all those requirements into a single natural ordering of the object.

`Comparator<T>` encapsulates a separate comparison rule. Its central method is:

~~~java
int compare(T left, T right);
~~~

The sign of the result plays the same role as in `compareTo`. The difference is where the rule lives:

| Criterion | Comparable | Comparator |
| --- | --- | --- |
| Where does the rule live? | Inside the element type | In an external comparator object |
| Primary method | `a.compareTo(b)` | `rule.compare(a, b)` |
| Suitable situation | A clear default ordering for the type | Ordering for a specific need or multiple sort orders |
| When used with TreeSet | No separate comparator needed | Pass the rule to the constructor |

Illustrative example for integers:

~~~java
SortedSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
~~~

This set uses the reverse of natural ordering. Adding `7, 2, 9, 5` will iterate as `[9, 7, 5, 2]`.

A provided `Comparator` solely determines the order of that set; there is no automatic step of "if the comparator sees equality, fall back to `compareTo`." If you want a secondary criterion, you must write or chain the secondary criterion explicitly.

Objects that do not implement `Comparable` can still live in a `TreeSet` if the provided `Comparator` supplies a valid comparison for the elements. That is why `Candidate` in the program does not need a `compareTo` method.

## 5. Understanding "Ascending" According to the Comparator Itself

When using reverse order, 9 comes before 2 because the comparator treats 9 as smaller than 2 under the order it defines. There is no contradiction between the ascending-iteration contract and the result `[9, 7, 5, 2]`.

Translate the words "first", "last", "smaller", and "larger" into the relationship of the current rule:

| Set | Iteration order | first() | last() |
| --- | --- | --- | --- |
| Natural order of Integer | `[2, 5, 7, 9]` | `2` | `9` |
| Reverse natural order | `[9, 7, 5, 2]` | `9` | `2` |

`first()` does not mean "the first element added." `last()` does not mean "the most recently added element" either. They rely on the set's ordering at the time of the call.

On an empty set, `first()` and `last()` throw `NoSuchElementException`. They do not use `null` as a general sentinel value for emptiness. This is especially worth noting when you provide a custom rule that allows `null`: a non-empty set can have `null` as its first element.

The `comparator()` method returns the comparator currently in use, or `null` if the set uses natural ordering. `comparator() == null` does not mean "unsorted", nor does it prove the set allows `null` elements. The two meanings of `null` belong to two different questions.

## 6. Comparison Returning 0 Determines Duplicates in a Sorted Set

Suppose the `Candidate` model has two components:

~~~text
name: name
score: score
~~~

And the input is:

~~~text
An:90
Binh:90
Chi:80
~~~

If the rule only compares `score`, it treats `An:90` and `Binh:90` as equivalent because:

~~~text
compare(An:90, Binh:90) = 0
~~~

A `TreeSet` using that rule keeps only one representative for the 90-score group. When adding `An` first and then `Binh`, the result in the example is `[Chi:80, An:90]`. The element count is 2, not 3.

This is not a bug where `TreeSet` forgot to compare names. You supplied a rule that ignores names, and the set used that exact rule to determine equivalence.

The consequence does not appear only in `add`. `contains(new Candidate("Unknown", 90))` can also return `true` in a set that only compares scores: there is already an order-equivalent representative, even though there is no candidate named `Unknown`. If you call `remove` with such an object, you can remove the representative of that score group.

This is why a set's `Comparator` should not be viewed merely as a display option. It participates directly in locating and distinguishing elements. With `TreeSet`, there is no additional hash check to distinguish two objects after the comparison returns 0. [Java 17: TreeSet, element comparison, and the Set contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

If the business logic needs to retain every candidate with the same score, "score" is not yet a sufficient criterion to distinguish elements in the set. You can add a criterion that fits the model, or use a sorted list if you need to keep every record including duplicates.

## 7. Chaining Criteria: Score Descending, Name Ascending

In the small model of this lesson, `Candidate` is a `record` consisting only of `name` and `score`. Its default `equals` checks both components. The names in the example are non-`null`.

We choose the order:

1. Higher score comes first.
2. If scores are equal, name in ascending order.

The rule is written as follows:

~~~java
Comparator<Candidate> ranking =
        Comparator.comparingInt(Candidate::score).reversed()
                .thenComparing(Candidate::name);
~~~

This snippet is used verbatim in the complete program. `Candidate::score` is a method reference: it retrieves a candidate's score. `comparingInt` creates an integer comparison; `reversed` reverses the direction of the score criterion; `thenComparing` uses the name only when the preceding criterion returns 0.

The three candidates are then iterated as:

~~~text
[An:90, Binh:90, Chi:80]
~~~

`An` and `Binh` have the same score but no longer compare as 0 because their names differ. Two objects both having `name="An"` and `score=90` still yield 0, consistent with the `equals` method of this `record` model.

Do not place `reversed()` arbitrarily. The expression:

~~~java
Comparator.comparingInt(Candidate::score)
        .thenComparing(Candidate::name)
        .reversed()
~~~

reverses the **entire** chained order: both score and name flip direction. It does not express "score descending, name ascending." This snippet is shown to contrast the scope of `reversed`, not as the rule used in the program.

Comparator chaining methods describe ordering criterion by criterion; read from left to right and identify exactly which segment is reversed. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

Names in the example do not replace a real-world candidate identifier. If a real system has a registration ID, uniqueness requirements and `equals` must be designed around that model. Do not arbitrarily add a random field as a secondary criterion and assume all identity issues are solved.

## 8. Consistency with equals Is a Condition Worth Checking

An ordering consistent with `equals` means that, for elements in the domain of use:

~~~text
compare(a, b) == 0  if and only if  a.equals(b)
~~~

For natural ordering, replace `compare(a, b)` with `a.compareTo(b)`. Equality to 0 here is order equivalence, not reference equality `a == b`.

The general `Set` contract is expressed in terms of `equals`. A sorted set instead uses comparison to determine equivalence. When the two relations do not match, the set still behaves deterministically according to the comparator, yet may not fully satisfy expectations of the `Set` contract.

In the program:

- The score-only rule merges `An:90` and `Binh:90` even though the record's `equals` distinguishes them. This example is intentionally designed to expose the mismatch.
- The score-then-name rule checks both components of the record, within the example's non-`null` name domain. Two objects compare equal to 0 only when they are equal according to `equals`.

Do not "fix" this by "never returning 0, even for the same object." Doing so breaks the comparison contract itself. A set is not a way to store duplicates by writing a comparator that pretends everything is always different.

A well-known exception in the JDK is `BigDecimal`. `new BigDecimal("1.0")` and `new BigDecimal("1.00")` are numerically equal according to `compareTo` but differ in `equals` because their representations have different scales. A `TreeSet` using natural ordering treats them as an equivalence group, and the second `add` returns `false`. The API explicitly notes this caveat when using `BigDecimal` in sorted sets or sorted maps. [Java 17: BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

You do not need to learn all of decimal arithmetic to take away the lesson: do not assume `compareTo == 0` always implies `equals == true` for every built-in type. When choosing an element type or a new comparator, check the actual equality rule.

## 9. The Comparator Must Be Valid Across the Entire Data Domain

An ordering rule must produce consistent, usable results, not just work on one sample pair of data.

Important conditions include:

- Swapping the two arguments must flip the sign of the result, with 0 remaining 0.
- The before/after relation must be transitive: if `a` comes before `b` and `b` comes before `c`, `a` must not come after `c`.
- If `a` and `b` compare equal to 0, their relationships with any third element must be compatible.

These rules are described in the `Comparable` and `Comparator` contracts. Do not use a comparison that depends on randomness or changes meaning between two calls for the same data. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

A common mistake is comparing integers by subtraction:

~~~java
// Illustrates a pattern to avoid when values may overflow.
Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

Two valid operands can still produce a difference outside the `int` range, causing the result's sign to be wrong. Use `Integer.compare(a, b)` or `Comparator.naturalOrder()` instead of inferring the sign from subtraction.

Also do not use a mutable state variable to silently change the rule after data has been added. The set does not tear down and rebuild its structure whenever a variable read by the comparator changes.

An easy-to-follow approach is to build a stable comparator, use standard comparison helpers, and test pairs with boundary values, equal primary criteria, and different secondary criteria. With the `record` models in this lesson, data immutability helps prevent the order from changing outside set operations.

## 10. Complete Program Using Java 17

Save the following code as `SortedSetOrderingDemo.java`. The program consists of independent example groups printed with clear labels:

- Integers in natural order and reverse order.
- `Version` providing its own `Comparable`.
- `Candidate` using a score-only comparator and a more complete comparator.
- `subSet` ranges, copying, and `null` policy.
- Expected exceptions and the `BigDecimal` case.

The `try/catch` blocks only demonstrate specific expected exceptions; they do not hide arbitrary errors across the whole program.

~~~java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedSetOrderingDemo {
    record Version(int major, int minor) implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int byMajor = Integer.compare(major, other.major);
            return byMajor != 0 ? byMajor : Integer.compare(minor, other.minor);
        }

        @Override
        public String toString() {
            return major + "." + minor;
        }
    }

    record Candidate(String name, int score) {
        @Override
        public String toString() {
            return name + ":" + score;
        }
    }

    public static void main(String[] args) {
        SortedSet<Integer> natural = new TreeSet<>();
        for (int number : new int[] {7, 2, 9, 2, 5}) {
            System.out.println("add " + number + "=" + natural.add(number));
        }
        System.out.println("natural=" + natural);
        System.out.println("natural comparator is null=" + (natural.comparator() == null));
        System.out.println("natural first/last=" + natural.first() + "/" + natural.last());

        SortedSet<Integer> reverse = new TreeSet<>(Comparator.reverseOrder());
        reverse.addAll(natural);
        System.out.println("reverse=" + reverse);
        System.out.println("reverse comparator is null=" + (reverse.comparator() == null));
        System.out.println("reverse first/last=" + reverse.first() + "/" + reverse.last());
        System.out.println("reverse subSet(9,5)=" + reverse.subSet(9, 5));

        SortedSet<Version> versions = new TreeSet<>();
        versions.addAll(List.of(new Version(1, 10), new Version(2, 0), new Version(1, 9)));
        System.out.println("versions=" + versions);
        System.out.println("version duplicate=" + versions.add(new Version(1, 10)));

        List<Candidate> input = List.of(
                new Candidate("An", 90),
                new Candidate("Binh", 90),
                new Candidate("Chi", 80));
        SortedSet<Candidate> scoreOnly =
                new TreeSet<>(Comparator.comparingInt(Candidate::score));
        scoreOnly.addAll(input);
        System.out.println("score only=" + scoreOnly);
        System.out.println("score only size=" + scoreOnly.size());
        Candidate stranger = new Candidate("Unknown", 90);
        System.out.println("different by equals=" + !input.get(0).equals(stranger));
        System.out.println("score only contains stranger=" + scoreOnly.contains(stranger));

        Comparator<Candidate> ranking =
                Comparator.comparingInt(Candidate::score).reversed()
                        .thenComparing(Candidate::name);
        SortedSet<Candidate> ranked = new TreeSet<>(ranking);
        ranked.addAll(input);
        System.out.println("ranked=" + ranked);
        System.out.println("ranked size=" + ranked.size());
        System.out.println("ranked duplicate=" + ranked.add(new Candidate("An", 90)));
        System.out.println("ranked contains stranger=" + ranked.contains(stranger));

        SortedSet<Integer> middle = natural.subSet(2, 9);
        System.out.println("middle initial=" + middle);
        middle.add(6);
        System.out.println("parent after view add=" + natural);
        natural.remove(5);
        System.out.println("middle after parent remove=" + middle);
        System.out.println("headSet(7)=" + natural.headSet(7));
        System.out.println("tailSet(7)=" + natural.tailSet(7));
        try {
            middle.add(9);
        } catch (IllegalArgumentException exception) {
            System.out.println("outside view=" + exception.getClass().getSimpleName());
        }

        SortedSet<Integer> copySame = new TreeSet<>(reverse);
        Collection<Integer> collectionInput = reverse;
        SortedSet<Integer> copyNatural = new TreeSet<>(collectionInput);
        System.out.println("sorted-set copy=" + copySame);
        System.out.println("collection copy=" + copyNatural);

        SortedSet<Integer> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(java.util.Arrays.asList(5, null, 2, null));
        System.out.println("nullable=" + nullable);
        System.out.println("nullable first=" + nullable.first());
        try {
            natural.add(null);
        } catch (NullPointerException exception) {
            System.out.println("natural null=" + exception.getClass().getSimpleName());
        }

        SortedSet<Candidate> missingRule = new TreeSet<>();
        try {
            missingRule.add(new Candidate("An", 90));
        } catch (ClassCastException exception) {
            System.out.println("missing ordering=" + exception.getClass().getSimpleName());
        }
        try {
            new TreeSet<Integer>().first();
        } catch (NoSuchElementException exception) {
            System.out.println("empty first=" + exception.getClass().getSimpleName());
        }

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal sameNumber = new BigDecimal("1.00");
        SortedSet<BigDecimal> decimals = new TreeSet<>();
        decimals.add(one);
        System.out.println("decimal equals=" + one.equals(sameNumber));
        System.out.println("decimal compare=" + one.compareTo(sameNumber));
        System.out.println("decimal second add=" + decimals.add(sameNumber));
        System.out.println("decimal size=" + decimals.size());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 SortedSetOrderingDemo.java
java SortedSetOrderingDemo
~~~

Use JDK 17 or later. The `--release 17` option checks code and APIs against Java 17; the filename matches the `public` class.

Expected output:

~~~text
add 7=true
add 2=true
add 9=true
add 2=false
add 5=true
natural=[2, 5, 7, 9]
natural comparator is null=true
natural first/last=2/9
reverse=[9, 7, 5, 2]
reverse comparator is null=false
reverse first/last=9/2
reverse subSet(9,5)=[9, 7]
versions=[1.9, 1.10, 2.0]
version duplicate=false
score only=[Chi:80, An:90]
score only size=2
different by equals=true
score only contains stranger=true
ranked=[An:90, Binh:90, Chi:80]
ranked size=3
ranked duplicate=false
ranked contains stranger=false
middle initial=[2, 5, 7]
parent after view add=[2, 5, 6, 7, 9]
middle after parent remove=[2, 6, 7]
headSet(7)=[2, 6]
tailSet(7)=[7, 9]
outside view=IllegalArgumentException
sorted-set copy=[9, 7, 5, 2]
collection copy=[2, 5, 7, 9]
nullable=[null, 2, 5]
nullable first=null
natural null=NullPointerException
missing ordering=ClassCastException
empty first=NoSuchElementException
decimal equals=false
decimal compare=0
decimal second add=false
decimal size=1
~~~

## 11. Reading Evidence from the Program

### 11.1. Position Depends on the Rule, Not Insertion Order

7 was added before 2, yet `natural` still iterates `[2, 5, 7, 9]`. The second `add` of 2 returns `false` because 2 is equivalent under natural ordering to an element already present.

`natural comparator is null=true` confirms there is no explicit comparator. It does not indicate that the set lacks ordering.

When the same data is placed into `reverse`, the result is `[9, 7, 5, 2]`. `first/last` switches to `9/2` because the two methods read the two ends of the active rule.

### 11.2. Comparable and Comparator Solve Two Ways of Providing Rules

`Version` implements `Comparable<Version>`, so `new TreeSet<Version>()` can use the natural ordering provided by the class. Comparing the major part first and the minor part second yields `[1.9, 1.10, 2.0]`.

`Candidate` does not implement `Comparable`. Two sets holding candidates still work when given a `Comparator`. However, `missingRule` receives no comparator and has no natural ordering from the element type, so adding a candidate leads to `ClassCastException`.

Being able to write `new TreeSet<Candidate>()` at compile time does not generate a `compareTo` method. The generic type of `TreeSet` does not force you to declare `E extends Comparable<E>`, because it must also support the `Comparator` case. You remain responsible for supplying one of the two valid comparison paths.

### 11.3. A Score-Only Comparator Affects Queries

`score only size=2` shows that one candidate was not added as a distinct element. `different by equals=true` yet `score only contains stranger=true` shows that the set's lookup uses score-based equivalence.

With `ranking` combining score and name, `ranked size=3` keeps all three distinct record values in the sample. `ranked contains stranger=false` because the name `Unknown` does not match any representative when all criteria are used.

Inspecting `size` and `contains` like this helps catch modeling errors before focusing solely on whether the printed string looks "in order."

### 11.4. Null Policy Must Be Specified in the Rule

The `nullable` set receives `Comparator.nullsFirst(Comparator.naturalOrder())`, so `null` is ordered before numbers. Two additions of `null` still produce one member, giving `[null, 2, 5]`.

`nullable first=null` is an actual element, not a signal of an empty set. Conversely, the integer set under natural ordering does not accept `null`, and the example prints the exception name `NullPointerException`.

### 11.5. Numerical Equality and Object Equality Can Differ

`decimal compare=0` accompanies `decimal equals=false`. The second decimal addition returns `false`, and the size is 1. The set uses `BigDecimal`'s ordering relation directly, without falling back to `equals` to try to distinguish further.

This example intentionally highlights the inconsistency between the two relations; it is not a recommendation to ignore representation differences when they matter for your data.

## 12. first, last, and Ordered Range Views

Beyond iteration, `SortedSet` provides the following basic operations:

| Method | Meaning under the current ordering |
| --- | --- |
| `comparator()` | Returns the explicit rule, or `null` if using natural ordering |
| `first()` | First element |
| `last()` | Last element |
| `subSet(from, to)` | Range from `from` (inclusive) to before `to` (exclusive) |
| `headSet(to)` | Range before `to` (`to` exclusive) |
| `tailSet(from)` | Range from `from` onward (`from` inclusive) |

The `SortedSet` range methods in the table use fixed boundary rules. Variants that let you choose inclusive/exclusive bounds via `boolean` parameters belong to `NavigableSet`, not the two-argument signature of `SortedSet.subSet`.

With natural ordering and the data `[2, 5, 7, 9]`:

~~~text
subSet(2, 9) → [2, 5, 7]
headSet(7)   → [2, 5]
tailSet(7)   → [7, 9]
~~~

Boundary values do not have to exist in the set. They represent range limits according to the comparison. For instance, on the initial set, `subSet(3, 8)` selects elements 5 and 7 even though neither 3 nor 8 is present.

With reverse order `[9, 7, 5, 2]`, the program uses `subSet(9, 5)` and receives `[9, 7]`. 9 is the start of the range under the comparator's order; 5 is the exclusive end boundary. Do not change it to `subSet(5, 9)` just because 5 is numerically smaller than 9: the two bounds must be valid according to the set's own ordering.

If the two bounds compare equal, `subSet(from, to)` is an empty range. If the start bound comes after the end bound under the active rule, the call does not represent a valid range.

## 13. Ranges Are Views Backed by the Original Set

`subSet` does not create an independent dataset. It returns a view backed by the original set. The program provides two-way evidence:

~~~text
initial natural: [2, 5, 7, 9]
middle:          subSet(2, 9) = [2, 5, 7]

middle.add(6)
natural:         [2, 5, 6, 7, 9]

natural.remove(5)
middle:          [2, 6, 7]
~~~

Adding through `middle` updates the original set. Removing an element within the range through the original set makes that element disappear when viewed through `middle`.

The view remains constrained by its chosen bounds. `middle.add(9)` is invalid because 9 is the exclusive end boundary. It throws `IllegalArgumentException`, even though the original set can validly contain 9.

The bounds act as an acceptance condition for the view, not just a one-time filter applied when creating the variable. After the view exists, adding a matching element to the original set can also make that element appear through the view.

If you need an independent snapshot, you can create a new set from the view with an appropriate rule choice. Copying a set creates structural membership independence; it does not automatically deep-clone each element object.

Be careful when passing a range view to another method: if the method removes from or clears the view, the corresponding data in the original set is also affected. When only reading is needed, the method's contract should state that clearly rather than letting the caller assume they received a copy.

## 14. Copying Can Preserve or Change Order Depending on the Constructor

`TreeSet` has multiple constructors. Two signatures that are easily misread as the same are:

~~~java
new TreeSet<>(aSortedSet);
new TreeSet<>(aCollection);
~~~

These are declaration patterns for comparison, with `aSortedSet` having type `SortedSet` and `aCollection` having type `Collection`.

The constructor taking a `SortedSet` preserves the source's ordering rule. The constructor taking a `Collection` creates a set using the elements' natural ordering. Those are two different contracts, even though the actual runtime source object may be the exact same `TreeSet`. [Java 17: TreeSet constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html#%3Cinit%3E(java.util.SortedSet)).

The program uses:

~~~java
SortedSet<Integer> copySame = new TreeSet<>(reverse);
Collection<Integer> collectionInput = reverse;
SortedSet<Integer> copyNatural = new TreeSet<>(collectionInput);
~~~

`reverse` has the declared type `SortedSet<Integer>`, so the first call selects the constructor that preserves the source ordering. `collectionInput` has the declared type `Collection<Integer>`, so the second call selects the constructor that uses natural ordering.

Therefore, the same members are copied into:

~~~text
sorted-set copy=[9, 7, 5, 2]
collection copy=[2, 5, 7, 9]
~~~

The key point is that overloaded constructor selection is based on compile-time type information. Do not assume the source's runtime class forces every copy call to preserve the comparator.

For objects without natural ordering, accidentally calling the `Collection` constructor can even cause an error rather than merely changing the sequence. When the ordering rule is an important requirement, pass the rule explicitly or keep the necessary source type.

## 15. null, Comparability, and Mutable Data

### 15.1. Null Policy Is Part of the Ordering

Natural ordering in the examples does not accept `null`. If you need to support it, a rule such as `Comparator.nullsFirst(Comparator.naturalOrder())` can define `null` as coming before other elements. `nullsLast` expresses placing it at the end.

This does not mean every `Comparator` automatically accepts `null`. A comparator calling `candidate.score()` will fail if the `candidate` argument is `null` without an appropriate wrapper.

Also distinguish two cases: the element itself being `null`, and a field inside the element being `null`. Wrapping the element comparator with `nullsFirst` does not automatically fix name comparisons where a name is `null` inside a non-`null` object. You must define the policy at the right data level.

### 15.2. Elements Must Be Mutually Comparable

A set using natural ordering requires more than "each object has a method named `compareTo`." Elements in the set must be mutually comparable under the type contract.

Using generics properly helps prevent many cases of mixing incompatible data. Do not use raw types to shove both `String` and `Integer` into the same set and expect a common ordering just because both implement `Comparable` in their own ways.

With `Comparator`, the rule must accept every valid element in the data domain you insert. If it only handles certain subclasses or assumes a field is always non-null when the data does not guarantee it, errors can occur during insertion, lookup, or range creation.

### 15.3. Do Not Mutate Sort Keys While an Element Is in the Set

Suppose the tree is organized by the `score` of a mutable object. After adding the object with score 50, you directly change that field to 95. `TreeSet` receives no `add/remove` call to know where to reposition the element.

As a result, observed ordering and lookups may no longer match the built structure. Similarly, changing a variable that a `Comparator` reads can silently alter the rule.

The simple design is to use immutable values for data participating in comparison. If you must update, perform a workflow of removing under the old state and then adding the new value under a clear contract; do not mutate first and assume `remove` will still locate the right position. The two `record` types in the program help keep ordering data stable.

## 16. Cost Belongs to the Implementation, Not Just the Interface Name

`SortedSet` is a behavioral contract, not a promise that every implementation uses the same algorithm. For `TreeSet`, the API documents `O(log n)` cost for `add`, `remove`, and `contains`, where `n` is the number of elements. That is the guarantee of the class used in this lesson.

The cost of the comparison itself still matters. Comparing a single integer differs from comparing multiple long string fields. A comparator that invokes I/O operations or reads constantly changing data is also unsuitable for a simple, stable ordering rule.

Do not describe `TreeSet`'s operation as "re-sorting an entire list on every insertion." The class maintains a structure suited to ordering to locate positions and perform set operations. This lesson does not need to rely on specific node shapes to use the API correctly.

If you only need to collect data and sort it once for display, a sorted list may be a better semantic fit, especially when you need to keep multiple elements with the same sort key. If you need a unique set that stays ordered and supports ordered range views throughout updates, `SortedSet` expresses that requirement more directly.

Sorted data does not automatically create thread safety when multiple threads modify concurrently. `TreeSet` is not synchronized by default. This decision is independent of using `Comparable` or `Comparator`; the lesson's program uses a single thread.

## 17. Common Pitfalls and How to Spot Them

| Reasoning error | Symptom or fix |
| --- | --- |
| "TreeSet preserves insertion order" | Inserting 7 then 2 still iterates 2 first; distinguish insertion order from comparison order |
| "Comparator only prettifies printed output" | Test `add`, `contains`, and deduplication with different objects sharing the same comparison key |
| "Same score still keeps everyone" | If only comparing score, comparison returns 0; add an appropriate distinguishing model or use a list |
| "After comparison returns 0, TreeSet checks equals" | There is no such additional distinguishing step |
| "compare must return exactly -1 or 1" | Check the sign of the result, not a fixed magnitude |
| "Subtracting two numbers is always a valid comparison" | Risk of overflow; use `Integer.compare` or standard helpers |
| "first is always the numerically smallest number" | Read the active rule; under reverse order, `first` is the largest number in the example |
| "comparator() returning null means unsorted" | `null` here indicates natural ordering is used |
| "subSet is a copy" | Mutate through the range and observe the original set |
| "Copying a TreeSet always preserves the comparator" | Check the constructor signature and the declared type of the source |
| "A record knows how to sort itself" | Records have default equality, not automatic `Comparable` |
| "Changing a sort field updates the tree automatically" | Use immutable data or an update workflow through the structure |
| "Every Comparable class is consistent with equals" | `BigDecimal` is a counterexample worth knowing |
| "A sorted Set fits every leaderboard" | Check requirements for keeping multiple records with the same key and uniqueness rules |

When results are missing elements, print or check `compare(a, b)` for two items you assumed were different. When results are in the wrong direction, check the scope of `reversed`. When range queries surprise you, read both bounds according to the comparator itself rather than numerical intuition.

## 18. Practice with Solutions

### Exercise 1: Natural Ordering

Add `8, 3, 8, 1, 5` in order to a `TreeSet<Integer>` without passing a `Comparator`. What is the final set and the result of the second addition of 8?

**Solution:** The final set is `[1, 3, 5, 8]`. The second addition of 8 returns `false`. Insertion order does not determine iteration order; duplicate occurrences do not create new members.

### Exercise 2: Reversing the Rule

Use the same data but create the set with `Comparator.reverseOrder()`. What are `first`, `last`, and `headSet(5)`?

**Solution:** The set is `[8, 5, 3, 1]`. `first()` is 8, `last()` is 1. `headSet(5)` contains elements before 5 under reverse order, so it is `[8]`. The bound 5 is excluded.

### Exercise 3: Missing Distinguishing Criterion

You have `Candidate("An", 90)` and `Candidate("Binh", 90)`. The comparator only compares scores. Can this set be used to retain the full list of candidates?

**Solution:** No, if those two candidates must be two distinct members. The comparison returns 0, so the set keeps only one representative for score 90. You need to define the uniqueness rule, add a model-compatible criterion, or choose a list if you want to keep all records.

### Exercise 4: Scope of reversed

Do the two expressions "score descending then name ascending" and "score ascending then name ascending, then reverse the whole thing" produce the same order?

**Solution:** No. The first expression reverses only the score criterion before chaining name. The second expression reverses both chained criteria, making names descending as well when scores are equal. Use two candidates with the same score and different names to verify the difference.

### Exercise 5: Range View

The natural set is `[1, 3, 5, 7]`. Create `view = set.subSet(2, 7)`, then call `view.remove(3)`. What are the original set and the view afterward? Can you call `view.add(7)`?

**Solution:** Initially the view is `[3, 5]`. Removing 3 through the view turns the original set into `[1, 5, 7]` and the view into `[5]`. You cannot add 7 through the view because the end bound is exclusive; the call throws `IllegalArgumentException`. Having 7 in the original set does not relax the view's limit.

### Exercise 6: Record Without Comparable

A new record contains `int id` and `String title`. You create `new TreeSet<ThatRecord>()` without passing a comparator. Since a record has `equals`, `hashCode`, and `toString`, can it automatically use natural ordering?

**Solution:** No. Those methods do not create `compareTo`. You must have the type implement `Comparable` with an appropriate rule or pass a `Comparator` to the set.

### Exercise 7: comparator() and null

A set of numbers has `comparator() == null`. Can you infer that it is unsorted or that it allows adding `null` elements?

**Solution:** No. The return value states that the set uses natural ordering. The policy for `null` elements is a separate question; `TreeSet<Integer>` under natural ordering in this lesson rejects `null`.

### Exercise 8: compareTo Differing from equals

Two numbers `BigDecimal("2.0")` and `BigDecimal("2.00")` give `compareTo` equal to 0 but `equals` equal to `false`. After adding both to a natural `TreeSet`, are there two elements?

**Solution:** No. The second element is equivalent in order, so it is not added as a separate member. If representation differences matter, you need an appropriate model and storage rule; do not assume a natural-ordering set retains both.

### Exercise 9: Natural Criterion of Version

With `Version` from the program, add `2.3, 1.20, 2.1, 1.4`. What order appears?

**Solution:** `[1.4, 1.20, 2.1, 2.3]`. Compare the major part first; only when major parts are equal compare the minor part numerically. Do not use the display string to infer the record's ordering.

## 19. Questions to Answer Before Choosing a Rule

Before putting a new data type into a `SortedSet`, determine:

- Does the type's natural ordering match the requirement, or is this a specific rule that should use a `Comparator`?
- Which two objects are allowed to compare equal to 0? Are they also equal according to `equals`?
- Are there distinct elements that must be kept even if they share the same score, name, or timestamp?
- Are all elements and boundary values mutually comparable?
- Is `null` allowed at the element level or on individual fields used for comparison?
- Can the data or state read by the rule change while the element is still in the set?
- When using `first`, `last`, and range views, are you reading "before/after" according to the comparator itself?
- When copying, do you need to preserve the source rule or intentionally create a different order?

After defining a rule, test at least one pair with equal primary keys and different secondary keys. Such a pair most clearly exposes the difference between "sorting records" and "deciding which records are the same member."
