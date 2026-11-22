# Consistency Between Comparator and equals

## 1. Why Check Both Comparator and equals

In `TreeSet`, the result `compare(a, b) == 0` determines whether two inputs belong to the same membership group. In the general `Set` contract, `equals` defines which values are duplicates. The two relations can produce different results, even when each relation is individually well-defined.

For example, `Comparator.comparingInt(String::length)` treats `"cat"` and `"dog"` as equivalent in length, whereas `String.equals` distinguishes them. A `TreeSet` ordered by length keeps only one representative. Another, subtler mismatch goes in the opposite direction: two objects that are equal according to `equals` can still be placed at different positions by a comparator.

This lesson examines **both directions** of the consistency condition, especially for types identified by an ID while displayed by a label. We also examine the consequences for `Set.equals`, and then design rules that fit the model. You need to know `Set`, `Comparator`, and `equals`; you do not need to know the internal details of tree nodes.

## 2. Three Expressions With Similar Names but Different Meanings

First, distinguish:

| Expression | Question answered |
| --- | --- |
| `a == b` | Do two reference variables point to the same object? |
| `a.equals(b)` | Are two elements equal according to the data type's rule? |
| `rule.compare(a, b)` | Does `a` come before, rank equivalent to, or come after `b` according to the ordering rule? |

For `compare`, only the sign of the result has a general meaning:

~~~text
result < 0 : a comes before b
result = 0 : a and b are equivalent in order
result > 0 : a comes after b
~~~

“Equality” in the title refers to **element `equals`**, not comparing two `Comparator` objects with each other. The `Comparator` interface also has an `equals(Object)` method, but `rule1.equals(rule2)` is a separate question about two comparators. Overriding that method is not how you make `compare(a, b)` match `a.equals(b)`.

Different references can still represent two equal values. For instance, two member objects with the same identifier can be treated by the model as the same person. Conversely, two words of the same length can still be two different string values.

Therefore, do not use `==` instead of `equals` when checking consistency. And do not treat a `compare` result of 0 as a numerical distance between two objects: it is an equivalence relation defined by the ordering rule.

## 3. The Two-Way “If and Only If” Condition

A `Comparator` is consistent with `equals` on the element domain under consideration when:

~~~text
(rule.compare(a, b) == 0) == a.equals(b)
~~~

holds for all valid non-`null` pairs of elements `a, b`. If the domain allows `null`, equality can be expressed with `Objects.equals(a, b)`, and the comparator must also handle those values.

The word “all” is crucial: not just the first pair or a few elements currently in the set. The rule must fit the entire data domain that the program allows to be inserted and queried.

The condition has two directions:

1. If the comparison returns 0, then the two elements must be equal according to `equals`.
2. If the two elements are equal according to `equals`, then the comparison must return 0.

A four-case table helps read this accurately:

| `a.equals(b)` | `compare(a, b) == 0` | Conclusion for this pair |
| --- | --- | --- |
| `true` | `true` | Both relations match |
| `false` | `false` | Both relations match |
| `false` | `true` | The comparator merges two values that `equals` distinguishes |
| `true` | `false` | The comparator separates two values that `equals` treats as one |

There is no requirement that `compare` return `hashCode(a) - hashCode(b)`. There is no requirement that `equals` return a position or sort direction. The two mechanisms have different responsibilities; what needs to match is the boundary between “equivalent” and “different”. [Java 17: Comparator, consistent with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 4. Why Does Set Need This Condition?

The general `Set` contract does not allow holding two elements that are equal according to `equals` at the same time. Addition operations, set equality, and set hash codes all depend on that identity rule. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

`TreeSet`, however, locates and distinguishes elements using natural ordering or the `Comparator` chosen when the set is created. When the comparison returns 0, it treats that as having found an equivalent member. It does not additionally call `equals` to separate two objects that the `Comparator` just grouped together.

You can picture two ways of partitioning data into groups:

~~~text
By equals:
  [cat] [dog] [owl]

By Comparator considering only length:
  [cat, dog, owl]
~~~

Each bracketed group represents elements considered the same value under the corresponding relation. In a set ordered by length, all three words belong to the same order-equivalence group. The set keeps one representative for that group.

If the two partitions match, the sorted set can both maintain order and satisfy the uniqueness semantics of `Set`. If they differ, “no duplicates” according to the tree no longer means “no duplicates” according to `equals`.

A valid comparator that is inconsistent with `equals` can still produce deterministic behavior in `TreeSet`. However, that set does not fully obey the general `Set` contract. This is a data-contract issue, not random element loss caused by a broken tree. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 5. First Mismatch Direction: Different Under equals, but compare Returns 0

With `Comparator.comparingInt(String::length)`, the three words `"cat"`, `"dog"`, and `"owl"` are three distinct values under `String.equals`, yet they fall into the same comparison group because all three are three characters long:

~~~text
"cat".equals("dog") = false
byLength.compare("cat", "dog") = 0
~~~

If you add `"cat"` and then `"dog"` to a `TreeSet` using that comparator, the second addition returns `false` and the set keeps only `"cat"`. `contains("owl")` still returns `true`, and `remove("owl")` removes the `"cat"` representative. Lookup and removal use the same comparison relation; calling `contains` before `add` does not resolve the mismatch.

The key check is **identity semantics**: if you only want to store the distinct lengths that appear, a set of length integers expresses that intent more clearly. If you want to store every word with distinct text, you must add a tie-breaking criterion that matches `String.equals`. The second mismatch direction, where `equals` treats two elements as one but the comparator separates them, requires looking more closely at the object model.

## 6. When Does Adding a Tie-Breaker Fix the Problem?

For `String`, you can sort by length first, and then by the full string content when lengths are equal:

~~~java
Comparator<String> lengthThenText =
        byLength.thenComparing(Comparator.naturalOrder());
~~~

Now `"cat"` and `"dog"` have the same length but are distinguished by content. Only two strings with identical content still produce 0 on both criteria.

The input `dog, a, cat, cat` produces the set:

~~~text
[a, cat, dog]
~~~

Length order is still preserved: `a` comes before the three-letter words. `cat` and `dog` coexist. The duplicate `cat` is eliminated in accordance with `String.equals`.

The condition for success here is not “any `thenComparing` will do”. It works because the final criterion distinguishes the exact values that `String.equals` distinguishes. If the secondary criterion still merges multiple distinct values, the problem remains.

For example, length followed by the first character is still not enough to distinguish `"cat"` and `"car"`. A secondary criterion that is useful for display is not necessarily sufficient for set uniqueness.

Nor should you use the hash code as a guaranteed identifier to distinguish all elements: two different objects can still share the same hash code. `hashCode` is not a collision-free global identifier.

## 7. Second Mismatch Direction: Equal Under equals, but compare Returns Non-Zero

Suppose a `Member` model has an `id` and a display `label`. The domain chooses identity by `id`: two objects with the same ID represent the same member, even if the label differs between two reads of the data.

In the program, `Member` is a record, but `equals` and `hashCode` are explicitly overridden to depend only on `id`. The default record `equals` over all components is not used.

The two values:

~~~text
7:alpha
7:zulu
~~~

are equal according to `equals`, because both have ID 7.

Now choose the rule “label first, ID second”:

~~~java
Comparator<Member> labelThenId =
        Comparator.comparing(Member::label).thenComparingInt(Member::id);
~~~

The labels `alpha` and `zulu` already differ on the first criterion. The comparator returns a non-zero result, so `TreeSet` accepts both:

~~~text
[7:alpha, 7:zulu]
size = 2
~~~

Viewed by order, the set has two distinct positions. Viewed by the `Set` contract based on `equals`, it is holding two equal elements.

Putting ID at the end does not fix this. `thenComparingInt` only runs when the preceding criterion returns 0. Once the label has already separated the two objects, having the same ID never gets a chance to make them equivalent.

Reversing it to “ID first, label second” does not fix it either: if the IDs are equal and the label is then used to break the tie, the final result is still non-zero for two objects that are equal according to `equals`. For an ordering to be compatible with ID-only equality, values with the same ID must always belong to the same equivalence group.

In the example, `Comparator.comparingInt(Member::id)` is the rule consistent with `Member.equals`. Adding `7:zulu` after `7:alpha` returns `false`. The stored representative remains `7:alpha`; matching the equality rule does not mean automatically updating the label from the later object.

## 8. Do Not “Fix” It With an Early Return 0 Branch and Arbitrary Sorting Elsewhere

A common idea is:

~~~java
Comparator<Member> shortcut = (left, right) ->
        left.id() == right.id() ? 0 : labelThenId.compare(left, right);
~~~

This snippet is used in the program to **demonstrate the bug**; it must not be passed into a `TreeSet`. It tries to guarantee 0 when IDs match, and sort by label when IDs differ.

With three values:

~~~text
a = 7:alpha
b = 7:zulu
c = 8:mike
~~~

we get:

~~~text
compare(a,b) = 0
a comes before c
b comes after c
~~~

If `a` and `b` are considered equivalent in order, they must have the same sign relative to every third element `c`. Here, one element of the same group comes before `c`, while the other comes after `c`. The equivalence group has no consistent position in the ordering.

This is a **Comparator contract violation**, not merely an inconsistency with `equals`. Having `compare == 0` match `equals` on every pair is not enough to prove that a comparator is valid.

A valid ordering must also guarantee sign reversal when swapping arguments, transitivity, and compatibility with any third element when comparison returns 0. Using a label criterion that can vary across objects with the same identity and then forcing them equal is an easy way to break this condition.

Do not rely on “adding a few elements seems to work” as a reason to use such a rule in a tree. The program only computes comparison results to expose the contradiction, avoiding building a structure on a comparator already known to be invalid.

## 9. Choose the Model First, Then Choose the Data Structure

If you identify by ID but want to display by label, separate those two needs clearly.

A common design is to store data by ID in a map, and then create a list of values sorted by label when needed for display. In that design:

- The ID determines which objects represent the same entity and which record gets updated.
- The list comparator determines how items are presented.
- Two label versions of the same ID are not admitted into a `TreeSet` as two separate members just because they sort to different positions.

Another option is to use immutable snapshot values whose `equals` covers the entire snapshot data. In that case, two snapshots with the same ID but different labels may intentionally be two distinct values. However, that is a change to the equality model; it must match actual requirements, not be done merely to make a particular comparator “valid”.

If the actual requirement is to group words case-insensitively, you can use a normalized key or a value type that embodies that equality rule along with a matching `hashCode`. Do not silently let one set treat `java/JAVA` as the same value while the rest of the system continues to treat them as two different strings.

For text data, normalization and comparison rules depend on the domain of use. The ASCII examples in this lesson do not automatically cover all locale or Unicode rules. Define key semantics explicitly instead of patching scattered places with case-folding calls.

## 10. Complete Program Verifying Both Directions

Save as `ComparatorEqualsDemo.java`. The program constructs its own data, requires no external libraries outside the JDK, and uses APIs available in Java 17.

The two methods `matchesEqualsOnSample` and `sameZeroClassSignsOnSample` are learning tools for checking a small sample. They are not a complete proof for all inputs of a `Comparator`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public class ComparatorEqualsDemo {
    record Member(int id, String label) {
        @Override
        public boolean equals(Object other) {
            return other instanceof Member member && id == member.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return id + ":" + label;
        }
    }

    static <T> boolean matchesEqualsOnSample(
            List<T> values, Comparator<? super T> rule) {
        for (T left : values) {
            for (T right : values) {
                if ((rule.compare(left, right) == 0) != Objects.equals(left, right)) {
                    return false;
                }
            }
        }
        return true;
    }

    static <T> boolean sameZeroClassSignsOnSample(
            List<T> values, Comparator<? super T> rule) {
        for (T left : values) {
            for (T right : values) {
                if (rule.compare(left, right) == 0) {
                    for (T third : values) {
                        if (Integer.signum(rule.compare(left, third))
                                != Integer.signum(rule.compare(right, third))) {
                            return false;
                        }
                    }
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Comparator<String> byLength = Comparator.comparingInt(String::length);
        SortedSet<String> coarse = new TreeSet<>(byLength);
        System.out.println("coarse add cat=" + coarse.add("cat"));
        System.out.println("coarse add dog=" + coarse.add("dog"));
        System.out.println("cat equals dog=" + "cat".equals("dog"));
        System.out.println("coarse compare=" + byLength.compare("cat", "dog"));
        System.out.println("coarse=" + coarse);
        System.out.println("coarse contains owl=" + coarse.contains("owl"));
        System.out.println("coarse remove owl=" + coarse.remove("owl"));
        System.out.println("coarse after remove=" + coarse);

        Comparator<String> lengthThenText =
                byLength.thenComparing(Comparator.naturalOrder());
        SortedSet<String> refined = new TreeSet<>(lengthThenText);
        refined.addAll(List.of("dog", "a", "cat", "cat"));
        System.out.println("refined=" + refined);
        System.out.println("refined consistent sample="
                + matchesEqualsOnSample(List.of("a", "cat", "dog"), lengthThenText));
        System.out.println("coarse consistent sample="
                + matchesEqualsOnSample(List.of("a", "cat", "dog"), byLength));

        Member alpha = new Member(7, "alpha");
        Member zulu = new Member(7, "zulu");
        Member mike = new Member(8, "mike");
        List<Member> members = List.of(alpha, zulu, mike);
        Comparator<Member> labelThenId =
                Comparator.comparing(Member::label).thenComparingInt(Member::id);
        SortedSet<Member> tooFine = new TreeSet<>(labelThenId);
        System.out.println("member equals=" + alpha.equals(zulu));
        System.out.println("label comparison sign="
                + Integer.signum(labelThenId.compare(alpha, zulu)));
        System.out.println("too fine first add=" + tooFine.add(alpha));
        System.out.println("too fine second add=" + tooFine.add(zulu));
        System.out.println("too fine=" + tooFine);
        System.out.println("too fine size=" + tooFine.size());
        System.out.println("too fine contains same id="
                + tooFine.contains(new Member(7, "probe")));

        Comparator<Member> byId = Comparator.comparingInt(Member::id);
        SortedSet<Member> identitySet = new TreeSet<>(byId);
        identitySet.add(alpha);
        System.out.println("by id second add=" + identitySet.add(zulu));
        System.out.println("by id=" + identitySet);
        System.out.println("by id contains same id="
                + identitySet.contains(new Member(7, "probe")));
        System.out.println("by id consistent sample="
                + matchesEqualsOnSample(members, byId));

        Comparator<Member> shortcut = (left, right) ->
                left.id() == right.id() ? 0 : labelThenId.compare(left, right);
        System.out.println("shortcut pair consistency="
                + matchesEqualsOnSample(members, shortcut));
        System.out.println("shortcut equal pair=" + shortcut.compare(alpha, zulu));
        System.out.println("shortcut third signs="
                + Integer.signum(shortcut.compare(alpha, mike)) + "/"
                + Integer.signum(shortcut.compare(zulu, mike)));
        System.out.println("shortcut zero class compatible="
                + sameZeroClassSignsOnSample(members, shortcut));

        Set<String> folded = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        folded.add("java");
        Set<String> exact = new HashSet<>(List.of("JAVA"));
        System.out.println("sorted equals hashed=" + folded.equals(exact));
        System.out.println("hashed equals sorted=" + exact.equals(folded));
        System.out.println("set hash codes equal=" + (folded.hashCode() == exact.hashCode()));

        BigDecimal shortForm = new BigDecimal("1.0");
        BigDecimal longForm = new BigDecimal("1.00");
        SortedSet<BigDecimal> numeric = new TreeSet<>();
        numeric.add(shortForm);
        System.out.println("decimal equals=" + shortForm.equals(longForm));
        System.out.println("decimal compare=" + shortForm.compareTo(longForm));
        System.out.println("numeric second add=" + numeric.add(longForm));
        System.out.println("numeric size=" + numeric.size());
        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
        SortedSet<BigDecimal> representations = new TreeSet<>(valueThenScale);
        representations.addAll(List.of(shortForm, longForm));
        System.out.println("representations=" + representations);
        System.out.println("representation consistent sample="
                + matchesEqualsOnSample(List.of(shortForm, longForm), valueThenScale));

        List<String> display = new ArrayList<>(List.of("cat", "dog", "cat"));
        display.sort(byLength);
        System.out.println("sorted list=" + display);
        System.out.println("sorted list size=" + display.size());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ComparatorEqualsDemo.java
java ComparatorEqualsDemo
~~~

Use JDK 17 or later. `--release 17` instructs the compiler to check code and APIs against Java 17. The `public` class name must match the file name.

Expected output:

~~~text
coarse add cat=true
coarse add dog=false
cat equals dog=false
coarse compare=0
coarse=[cat]
coarse contains owl=true
coarse remove owl=true
coarse after remove=[]
refined=[a, cat, dog]
refined consistent sample=true
coarse consistent sample=false
member equals=true
label comparison sign=-1
too fine first add=true
too fine second add=true
too fine=[7:alpha, 7:zulu]
too fine size=2
too fine contains same id=false
by id second add=false
by id=[7:alpha]
by id contains same id=true
by id consistent sample=true
shortcut pair consistency=true
shortcut equal pair=0
shortcut third signs=-1/1
shortcut zero class compatible=false
sorted equals hashed=true
hashed equals sorted=false
set hash codes equal=false
decimal equals=false
decimal compare=0
numeric second add=false
numeric size=1
representations=[1.0, 1.00]
representation consistent sample=true
sorted list=[cat, dog, cat]
sorted list size=3
~~~

## 11. Reading the Output by Contract

### 11.1. Merging Too Many Values

`coarse add dog=false` confirms that `dog` does not get its own entry after `cat`. `cat equals dog=false` alongside `coarse compare=0` confirms the first mismatch direction.

`coarse contains owl=true` and `coarse remove owl=true` show that the mismatch affects both lookup and removal. After the remove call, the set is empty even though the string passed to remove was never added.

You cannot conclude that `remove` found the same reference or the same string content. It found an element equivalent according to the comparator.

### 11.2. A Secondary Criterion Matching Equality

`refined=[a, cat, dog]` preserves the distinct strings while still eliminating the duplicate `cat`. `refined consistent sample=true` indicates that on the supplied sample, every pair matched the `compare == 0` and `equals` condition.

Reasoning from the rule structure is stronger than a sample result: for non-`null` strings, comparing full content as the final criterion returns 0 only when the contents are equal. Thus we know why that rule fits `String.equals`, rather than merely seeing three words handled properly.

### 11.3. Separating Equal Objects

`member equals=true` while `label comparison sign=-1` shows that two members with the same ID are separated by the label rule. Both additions return `true`, and the size is 2.

`too fine contains same id=false` uses an object with ID 7 and label `probe`. Although it equals the ID-7 members under `equals`, the lookup does not find an equivalent position by label. Thus, not only is the count wrong for the identity semantics; membership checks are skewed as well.

### 11.4. Fixing by Using the True Identity

With `byId`, the second addition with the same ID returns `false`, the set keeps `[7:alpha]`, and querying with ID 7 and a different label returns `true`.

This matches the model's equality rule. If the goal is to replace the existing label, you need an update operation under a different contract; do not infer from `add` returning `false` that `zulu` was merged into the old object.

### 11.5. Pairwise Checking Is Not Enough

`shortcut pair consistency=true` appears on the three-member sample, yet `shortcut third signs=-1/1` and `shortcut zero class compatible=false` expose the contradiction with the third element.

The pairwise check function is not wrong: it simply checks the exact property it was assigned. The mistake would be interpreting its result as a complete proof of comparator validity.

That is how any test should be read: a `true` result is meaningful only within the scope of the property and data tested.

## 12. Mismatch Can Break Symmetry of Equality Between Two Sets

The program creates two sets, each with one element:

~~~text
folded: TreeSet using case-insensitive comparison, containing "java"
exact:  HashSet using String.equals, containing "JAVA"
~~~

Neither string's content is modified. The two structures use two different interpretations of “contains this value”.

Output:

~~~text
sorted equals hashed=true
hashed equals sorted=false
~~~

Under the standard `equals` contract, if `x.equals(y)` is `true`, then `y.equals(x)` must also be `true`. The two results here expose the incompatibility caused by the sorted set using an ordering inconsistent with `String.equals`. This should not be interpreted as permission to pick whichever direction of `equals` gives the desired result. [Java 17: Object.equals, symmetry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

The reason in the example's classes can be traced directly. The `equals` implementation inherited from `AbstractSet` checks for equal size and then asks whether the receiving set contains every member of the other set.

- `folded.equals(exact)` uses `folded`'s containment check. The string `JAVA` is equivalent to `java` under the case-insensitive comparator, so the result is `true`.
- `exact.equals(folded)` uses `HashSet`'s containment check with `String.equals`. The string `java` differs from `JAVA`, so the result is `false`.

This is a single-element example to eliminate any effect of iteration order or size. The root issue is that the two equality relations do not match.

Not every dataset with an inconsistent comparator will immediately expose a broken `equals`. One counterexample is enough to know that you can no longer rely on the general contract.

## 13. hashCode Still Matters Even Though TreeSet Does Not Search by Hashing

You might think that using a tree means you do not need to care about `hashCode`. Two roles must be separated:

1. How `TreeSet` locates member positions relies primarily on comparison.
2. The set itself and its elements are still Java objects with an `equals/hashCode` contract.

In the program, `Member.equals` is overridden by ID, so `Member.hashCode` is also based on ID. Two equal members with ID 7 must have the same hash code, even if their labels differ. This is a requirement of the object itself, independent of whether you put it into a `HashSet` or a `TreeSet`.

The hash code of a set per `AbstractSet` is computed from the hash codes of its elements, not from the semantics of its `Comparator`. For the `java/JAVA` example, the program prints:

~~~text
set hash codes equal=false
~~~

While one direction of `equals` just returned `true`, this result also exposes a violation of the requirement that equal objects must have the same hash code. Changing a single set's hash function to group by its comparator would not fix the mismatch with `String.equals` elsewhere. [Java 17: AbstractSet.equals and hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

You cannot fix an inconsistent `Comparator` by adding `hashCode` into the comparison. Hash codes only need to be equal for equal values; they are allowed to collide for different values. They do not provide a complete ordering in place of the value model.

## 14. Natural Ordering Must Also Be Checked: BigDecimal

The issue is not limited to lambdas you write yourself. A `TreeSet` constructed without a custom `Comparator` uses natural ordering from `Comparable`, and the equivalence relation of `compareTo` can also differ from `equals`.

With:

~~~text
new BigDecimal("1.0")
new BigDecimal("1.00")
~~~

`compareTo` returns 0 because they have the same numeric value. `equals` returns `false` because in addition to numeric value, it considers representation by `scale`. In this sample, the scales are 1 and 2, respectively.

The program outputs:

~~~text
numeric second add=false
numeric size=1
~~~

This is the behavior of the type's natural ordering. The `BigDecimal` documentation notes this difference and advises caution when using it in sorted structures. [Java 17: BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

If you want to distinguish representations according to `BigDecimal.equals`, the example uses:

~~~java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
~~~

It compares numeric value first; when values are equal, it compares `scale`. Equal numeric value and equal `scale` match `BigDecimal`'s equality. Both representations are kept as `[1.0, 1.00]`.

This is not rounding, nor does it alter the numeric value or scale of the objects. It simply chooses an ordering that further distinguishes what `equals` distinguishes.

If the domain only needs uniqueness by numeric value, choose a key model that expresses that intent and use it consistently. Do not assume that representation differences always matter or must always be discarded; that is a data decision, while this lesson simply points out the two existing relations.

## 15. An Inconsistent Comparator Can Still Be Used to Sort a List

Being inconsistent with `equals` does not automatically mean a comparison violates every contract. The string-length comparator still defines a clear group ordering and can be used to sort a list of words.

The end of the program outputs:

~~~text
sorted list=[cat, dog, cat]
sorted list size=3
~~~

`List.sort` reorders elements; it does not perform `TreeSet`-style deduplication. Therefore, using the length criterion does not cause `dog` or the duplicate `cat` to disappear. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Distinguish the requirements:

| Need | Structure and rule to consider |
| --- | --- |
| Keep all records, only change display order | A `List` and a valid `Comparator` for presentation |
| Keep one element per `equals` value, always ordered | A sorted set with an ordering consistent with `equals` |
| Identify and update by ID, display by another field | Storage structure keyed by ID, plus a list/view for presentation |
| Intentionally group by a separate key | An explicit key or grouping model, not silently conflated with the original data's `equals` |

A `Comparator` used for a list must still obey the comparison contract. The `shortcut` example that fails with a third element does not become valid just by moving from a tree to a list.

What is allowed to differ here is the 0-comparison relation versus `equals` when the operation only needs a suitable sort order. Not every tie in rank has to make two objects the same domain entity.

## 16. How to Test Meaningfully

For a new rule, prepare test pairs tailored to the model's properties:

- Same reference.
- Different references that are equal according to `equals`.
- Same primary sort key, but differing in an attribute that `equals` checks.
- Different primary sort keys.
- Boundary values of numeric or string fields.
- `null` values only when the contract actually allows them.

`matchesEqualsOnSample` compares every pair in the sample and checks whether `compare == 0` and `Objects.equals` have the same `boolean` value. It does not care whether the comparator returns -1, -20, or 20; it only needs to distinguish 0 from non-zero for this property.

In addition, check the ordering properties:

~~~text
swap two arguments → flip sign
a before b, b before c → a before c
a equivalent to b → they must have the same direction relative to every c
~~~

`sameZeroClassSignsOnSample` checks only the last property on the sample, not all remaining properties. Its name intentionally limits what it claims.

Pairwise checking cost grows quadratically with the number of elements; triple checking grows cubically. The functions in this lesson are suited for small samples chosen to illustrate behavior and find counterexamples, not as checks to re-run after every insertion into a real set.

A passing sample test does not prove correctness over an infinite domain. Combine runtime evidence with reasoning about the attributes used by `equals` and `Comparator`. A sample containing two label versions of the same ID is usually far more useful than many records where every ID and every label is distinct.

## 17. Data and Rules Must Remain Stable While Stored

Consistency is not just a snapshot at a single point in time. If you mutate a field used in comparison while the object is still inside a `TreeSet`, the tree does not automatically know to reorganize its positions.

If `equals` relies on one set of fields and `Comparator` relies on another, mutating data can both break tree lookup and alter the relationship between two objects.

An easy way to keep control is to use immutable values for attributes involved in ordering and identity. For instance, `Member` uses record components with no setter operations; two different labels are represented by two different objects so we can observe the rule clearly.

Do not keep a comparator that depends on silently mutable configuration, such as a reverse flag flipped after the set has been created. An ordering that is valid at insertion time but changes meaning during lookup is not a stable foundation for a sorted structure.

Also avoid fake tie-breakers like returning 1 for two equivalent elements, using random numbers, or using synthetic addresses to force a set to keep everything. They do not replace a value model and can break sign-symmetry or transitivity.

## 18. Common Misconceptions to Correct When Reading Code

| Misconception | What to check |
| --- | --- |
| “Two different objects, so `compare` must be non-zero” | “Different references” does not mean “different under `equals`” |
| “As long as `compare == 0` implies `equals` is true, it’s fine” | You also need the reverse: `equals` true implies `compare == 0` |
| “`TreeSet` will fall back to `equals` if the comparator isn’t fine-grained enough” | The set uses the comparison result to determine equivalence |
| “Adding `thenComparing(id)` always fixes it” | Check the case with the same ID but a different preceding criterion |
| “Returning 0 early when `equals` is true is enough” | You must check the relationship with third elements and transitivity |
| “`hashCode` is a reliable universal tie-breaker” | Hash codes are allowed to collide |
| “Same `hashCode` means `equals` is true” | The contract only requires equal values to have the same hash code |
| “Records identify by `id` by default” | Records check all components by default; this lesson explicitly overrides `Member` |
| “One direction of `set.equals` returning true is enough” | `equals` must be symmetric and compatible with `hashCode` |
| “Built-in natural ordering always matches `equals`” | `BigDecimal` is a key case to know |
| “If it’s inconsistent with `equals`, the comparator cannot be used to sort” | A valid `Comparator` can still sort a list; separate ordering from uniqueness |
| “A passing sample check proves all data is handled correctly” | Analyze the data domain, model properties, and targeted counterexamples |
| “`equals` here means `Comparator.equals`” | We are checking element `equals`, not equality of two comparator objects |

Bugs are hardest to spot when every sort key in the test sample is distinct. Proactively construct data with duplicate primary keys and versions that share an identity but differ in other fields before drawing conclusions.

## 19. Practice Exercises With Solutions

### Exercise 1: Checking Both Directions

A pair of objects has `a.equals(b) == false` and `compare(a,b) == 0`. Is that pair consistent? What if it is reversed to `equals == true` and `compare != 0`?

**Solution:** Neither is consistent. In the first case, the comparator merges too many values; in the second, it separates values that `equals` treats as one. Both directions of the condition must be checked.

### Exercise 2: Predicting Lookup and Removal

A string set using a length-only comparator currently contains `"red"`. What do `contains("sky")` and `remove("sky")` return?

**Solution:** Both return `true` in this example because both strings have length three. The removal deletes the `"red"` representative from the set. It does not require `"sky"` to have ever been added.

### Exercise 3: One Secondary Criterion Is Not Enough

You compare strings by length, then by the first character. Are `"cat"` and `"car"` still merged?

**Solution:** Yes. They have the same length and the same first character, so both criteria return 0. For `String` equality, you need a final criterion capable of distinguishing the entire content, such as natural string ordering.

### Exercise 4: ID First, Label Second

`Member` has `equals` based only on ID. The comparator compares ID first, and if equal, compares label. Are `5:old` and `5:new` consistent?

**Solution:** No. `equals` treats the same ID 5 as equal, but the label criterion separates them into a non-zero comparison result. Putting ID first does not automatically eliminate the effect of the secondary criterion.

### Exercise 5: Why Is an Early Return 0 Branch Not Enough?

Given `a=7:alpha`, `b=7:zulu`, and `c=8:mike`. The rule returns 0 when IDs match, and compares labels when IDs differ. Which condition is broken?

**Solution:** `a` and `b` compare as 0, yet `a` comes before `c` while `b` comes after `c`. Order-equivalent objects must have the same sign when compared to any third element. This rule violates the `Comparator` contract, even though the pairwise `compare == 0` check matches `equals` on the sample.

### Exercise 6: Choosing a Model

You need one person per unique ID, frequently update display names, and occasionally output a list sorted by name. Should you use a `TreeSet` sorted by name then ID for both storage and updates?

**Solution:** Be careful: two name versions of the same ID can become two separate elements if `equals` is by ID. A structure that stores/updates by ID and a list sorted by name for presentation usually separates those two needs properly. Choose the model before choosing the comparator.

### Exercise 7: Two Sets and Symmetry

A case-insensitive `TreeSet` contains `"abc"`; a `HashSet` contains `"ABC"`. Should you use a one-way `equals` result to claim the two sets are interchangeable in all `Set`-handling code?

**Solution:** No. The two sets use two different identity relations. As the program showed with `java`/`JAVA`, equality can differ when reversed and cause `hashCode` contract issues. Unify the key model rather than picking a convenient call direction.

### Exercise 8: Sorting a List

A list containing `cat, dog, cat` is sorted by length. Does a comparator that is inconsistent with `String.equals` cause the list to automatically drop `dog`?

**Solution:** No. Sorting a list does not deduplicate elements the way `TreeSet` does. All three elements remain. The comparator must still be valid for ordering; the difference is that a list does not use `compare == 0` to drop members.

### Exercise 9: BigDecimal

You want to keep `3.0` and `3.00` distinct according to `BigDecimal.equals`. Does using natural ordering alone in `TreeSet` satisfy that? What criterion could be added after value comparison?

**Solution:** Natural ordering gives `compareTo` equal to 0, so it does not keep two separate members. The example in the lesson adds `scale` after numeric value comparison to distinguish representations according to `BigDecimal`'s equality. That does not round or alter the data.

### Exercise 10: Reading the Scope of a Check

`matchesEqualsOnSample` returns `true` on ten objects. Can you conclude the comparator is valid and consistent on all data of the class?

**Solution:** No. The method only checks the `compare == 0` vs. `equals` relation on pairs in the sample; it does not check the full ordering contract or cover the entire domain. The `shortcut` example is direct evidence that passing one property does not substitute for another.

## 20. Short Checklist When Reviewing a Comparator Used for a Set

First, write down in words the definition of element `equals`. Then, write down the exact condition for the `Comparator` to return 0. Those two conditions must coincide on the allowed data domain if you want to obey the general `Set` contract.

Next, check ordering validity with triples of elements, especially when there is a special branch for “same ID”. Check whether any fields used for comparison can mutate while stored.

Finally, test `add`, `contains`, and `remove` using a different object reference that has the same domain value. When the system exchanges data between different `Set` implementations, check both directions of `equals` and `hashCode` compatibility.

If the rule you need is only for display, place it in the appropriate presentation-sorting layer. Do not force a single sorted set to simultaneously solve two different definitions of “the same element”.
