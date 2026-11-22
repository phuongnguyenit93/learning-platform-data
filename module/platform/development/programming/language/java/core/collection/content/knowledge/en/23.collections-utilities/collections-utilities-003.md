# min, max, frequency, and disjoint

Many questions about a collection only need a small result: the lowest element, the highest element, how many times a value appears, or whether two groups overlap. You do not need to sort an entire list or build an intersection collection yourself just to answer those questions.

`Collections.min` and `Collections.max` select an element according to an ordering. `Collections.frequency` counts elements equal to a given value by `equals`. `Collections.disjoint` answers whether two collections have **no elements in common**.

A common pitfall is assuming every method uses the same definition of "equality." A comparator, `equals`, and how a collection determines membership can differ. This lesson separates each contract clearly, then verifies them with runnable Java 17 code.

## 1. Choosing a method from the question you need to answer

| Question | Method | Result | Does it reorder or modify the collection? |
| --- | --- | --- | --- |
| What is the smallest element according to an ordering? | `min(collection)` or `min(collection, comparator)` | An element `T` | No modification needed |
| What is the largest element according to an ordering? | `max(collection)` or `max(collection, comparator)` | An element `T` | No modification needed |
| How many elements are equal to the target value? | `frequency(collection, value)` | `int` | No modification needed |
| Do two collections have no elements in common at all? | `disjoint(left, right)` | `boolean` | No modification needed |

These methods accept `Collection`, not just `List`. Lists, sets, and many other collections are valid inputs. They do not require the collection to support `add`, `remove`, or `set`.

`Map` is not a subtype of `Collection`. When working with a map, choose the right view such as `keySet()`, `values()`, or `entrySet()` so the question makes sense.

A small return value does not mean the work is always constant time. To find the largest element in a collection without a dedicated supporting structure, you usually have to iterate through the elements. You must distinguish the amount of data returned from the amount of data that needs to be read.

## 2. `min` and `max` by natural ordering

### No need to sort the input

The following snippet is illustrative code inside a method with all necessary imports:

~~~java
List<Integer> values = List.of(9, 2, 7, 2);

int lowest = Collections.min(values);
int highest = Collections.max(values);
~~~

`lowest` is 2 and `highest` is 9. The list still has the order `[9, 2, 7, 2]`; both `2`s are still present. No sorting, deduplication, or element replacement occurs in the list.

`min` and `max` return the **element**, not its index. For collections without indexed access, a question about index would not make sense anyway.

### Natural ordering comes from `Comparable`

The overload without a comparator requires elements to have a natural ordering and be mutually comparable. For `Integer`, that is numerical order.

If a domain class does not implement `Comparable`, you should not expect `min` to guess whether to use price, age, or name. Provide an appropriate comparator instead.

If you bypass generics using raw types and mix incomparable types, the call may throw `ClassCastException` when comparison is needed. Proper generics express and check intent at compile time. [Natural ordering and Comparable, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

### Traversing and tracking a single candidate

Finding the minimum can be understood as follows:

1. Pick one element as the initial candidate.
2. Read the remaining elements one by one.
3. Whenever an element is smaller under the active ordering, replace the candidate.
4. After traversing all elements, the candidate is a minimal element.

`max` works the same way, keeping the larger candidate. This approach does not need to reorder elements or create a sorted list.

That is also why unmodifiable lists work with these queries. Not having permission to modify a container does not mean you cannot compute over its contents.

## 3. A Comparator defines what "smallest" and "largest" mean

### Choosing a domain field

Suppose each offer has a code and a numeric cost:

~~~java
record Offer(String code, int cost) {
}

Comparator<Offer> byCost =
        Comparator.comparingInt(Offer::cost);
~~~

Then:

~~~java
Offer cheapest = Collections.min(offers, byCost);
Offer mostExpensive = Collections.max(offers, byCost);
~~~

These are illustrative snippets assuming the variable `offers` already exists; the complete program below declares all the data.

The result is an `Offer`, not just the `cost` value. To get the number, read `cheapest.cost()` after selecting the element.

A comparator should describe a consistent, stable relation throughout the traversal. Do not compare using integer subtraction, which can overflow; use `Integer.compare` or `comparingInt`. Do not change the comparison key field mid-traversal. [Comparator contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Reversing a comparator also flips the meaning of min/max

With the numbers `[9, 2, 7, 2]`:

~~~java
int firstInDescendingOrder =
        Collections.min(values, Comparator.reverseOrder());
~~~

The result is 9. It is the "smallest" element **according to the descending comparator**, even though it is the largest number in natural order.

Similarly, `max(values, Comparator.reverseOrder())` returns 2. Do not read the name `min` in isolation from the comparison rule you passed.

If the goal is to pick the naturally largest number, `max(values)` is easier to read than using `min` with a reversed comparator. A reversed comparator is useful when it is part of a business rule, but variable names should still reflect the true meaning.

### A set's comparator is not used automatically

A `TreeSet` may iterate using its own comparator, such as descending order. That does not change the contract of `Collections.min(collection)` into "take the first element according to the set's comparator."

With a descending set containing 2, 9, and 4:

- `tree.first()` is 9 according to the order maintained by the set.
- `Collections.min(tree)` is 2 according to natural ordering.
- `Collections.min(tree, tree.comparator())` is 9 according to the explicitly passed descending comparator.

Distinguish between "the order maintained by the structure" and "the order chosen by the query." If you want to use the set's rule, you must pass it explicitly or use a specialized operation with the right contract. [How TreeSet uses a comparator, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### Multiple elements tied for the extremum

Suppose A and B both have `cost` equal to 50. If the comparator only compares cost, both are valid candidates for min.

The contract for selecting an extremum should not be interpreted as a promise to pick a specific code among tied elements. If the requirement is "lowest cost; if tied, lowest code," write a tie-breaker criterion:

~~~java
Comparator<Offer> byCostThenCode =
        Comparator.comparingInt(Offer::cost)
                .thenComparing(Offer::code);

Offer selected = Collections.min(offers, byCostThenCode);
~~~

Do not rely on a current run's output to assign business meaning to an unspecified tie-breaking order. If you only care about the minimum cost, testing the cost value is more accurate than forcing a specific code to win when the comparator does not distinguish codes.

## 4. Empty collections, `null`, and return values

### No min/max when there are no elements

`Collections.min` and `Collections.max` throw `NoSuchElementException` on an empty collection. They do not return 0, do not create a default object, and do not use `null` as a general marker for "no elements." [min/max contract in Collections, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#min(java.util.Collection)).

How you handle this depends on your application's API:

- If missing data is a valid state, check for it and represent the absence explicitly.
- If the business logic requires data, report an error with appropriate context.
- Only use a default value when it truly makes sense, not just to suppress the exception.

For example, 0 is not always an appropriate minimum for an empty dataset: it could be misinterpreted as an actual observation with value 0.

Checking `isEmpty` and then reading the data requires the source to remain in a consistent state. If another party can modify the collection between the two steps, a pre-check does not create a transaction.

### `null` is only ordered if the rule allows it

Just because a collection allows `null` does not mean natural ordering handles `null` during comparison. For data containing `null`, pass a comparator with an explicit policy:

~~~java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

String min = Collections.min(values, nullLast);
String max = Collections.max(values, nullLast);
~~~

If `values` is `["x", null, "x", null]`, min is `"x"` and max is `null`. `null` is treated as greater than non-`null` strings, so it can be a **valid result element**.

With `nullsFirst`, the priority of `null` is reversed. Passing a `null` comparator to the comparator overload means falling back to natural ordering, not ignoring `null` elements.

Do not use a special collection with very few elements to infer that comparing `null` is always safe: in some cases the algorithm might not need to compare any pair. The comparator's policy is what matters when comparison is needed.

If your model allows an actual min/max to be `null`, do not conflate that result with "empty collection." A wrapper that cannot represent a present `null` value can lose this distinction; the result design must fit the specific model.

### The result is not a defensive copy

When elements are mutable objects, `min`/`max` returns an existing element from the collection rather than cloning it. If the caller mutates the selected object, the collection still holds a reference to that same object.

The fact that queries do not modify the collection during selection does not mean the returned object is isolated for reading. Apply ownership policies or immutable representations if the API must not expose live objects.

## 5. `frequency`: counting by `equals`, not by comparator

### The question is "how many elements equal this value?"

~~~java
List<String> labels = Arrays.asList("x", null, "x", null);

int xCount = Collections.frequency(labels, new String("x"));
int nullCount = Collections.frequency(labels, null);
~~~

Both results are 2. The new string object is still equal to the `"x"` strings by `equals`; it does not need to be the same reference.

The formal definition counts elements `e` such that `Objects.equals(value, e)`. When the target value is `null`, `null` elements are counted. When no elements match, the result is 0. [frequency API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#frequency(java.util.Collection,java.lang.Object)), [Objects.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

An empty collection also returns 0. Conversely, passing `null` as the collection itself is not an empty collection and will cause a `NullPointerException`.

### No comparator overload

With `Offer("A", 50)` and `Offer("B", 50)`, a comparator by cost returns 0, but the two records are not equal across all components.

If a list contains those two offers:

- Counting `new Offer("A", 50)` gives 1.
- Counting `new Offer("X", 50)` gives 0 even though the cost is also 50.
- To count all offers with cost 50, you need a field check or an appropriate mapping step.

A loop expresses the intent clearly:

~~~java
int matchingCost = 0;
for (Offer offer : offers) {
    if (offer.cost() == 50) {
        matchingCost++;
    }
}
~~~

Do not try to pass a comparator to `frequency`; the API has no such overload. You must choose between "object equality" and "matching a business condition."

### Do not use a set's lookup rule to replace the definition of frequency

A case-insensitive `TreeSet<String>` can hold `"red"` and return `true` for `contains("RED")`. However, `frequency(set, "RED")` counts using `String.equals`, so it does not count that `"red"` element.

There is no contradiction: the two calls use two different rules. In a set that follows standard `equals` semantics, the frequency of a value is 0 or 1; for structures using different rules, fall back to the exact contract of each operation.

`frequency` also does not count substrings. A list containing `"Java"` twice does not make the frequency of `"Ja"` equal to 2. It counts whole elements equal to the target object.

## 6. `disjoint`: `true` means no elements in common

### Reading the negation in the right direction

~~~java
List<String> requested = List.of("READ", "WRITE", "READ");
Set<String> blocked = Set.of("DELETE", "WRITE");

boolean noOverlap = Collections.disjoint(requested, blocked);
~~~

The result is `false` because `"WRITE"` is in common. If you want a variable expressing "overlaps," negate it explicitly:

~~~java
boolean overlaps = !Collections.disjoint(requested, blocked);
~~~

Variable naming is important for reading logic correctly. Do not name a variable `hasCommon` and assign the result of `disjoint` directly to it if that inverts the meaning.

Duplicate elements do not change the existence answer: a single shared value is enough for `disjoint` to return `false`. The method does not return the overlap count and does not build an intersection collection.

### Empty collections and the same collection instance

With valid collections and compatible query elements:

- If one side is empty, there are no common elements, so the result is `true`.
- If both sides are empty, the result is still `true`.
- Passing the same non-empty collection on both sides gives `false`.
- Passing the same empty collection on both sides gives `true`.

A non-empty collection naturally has elements in common with itself. There is no need to make a copy just to call this check.

### Can stop as soon as a common element is found

The query idea is to read elements from one collection and check membership in the other. Once a common element is found, it is enough to return `false`; there is no need to enumerate the entire intersection.

Do not rely on the call order of `contains` or assume the left side is always the one iterated. The implementation is free to choose either side or an equivalent computation.

This also affects the design of collections with element-type restrictions or special matching rules, as shown in the next section.

## 7. Compatibility conditions for `disjoint`

### Elements must be valid query inputs for both sides

One collection containing `null` and the other disallowing `null` can throw `NullPointerException` depending on the lookup operation performed. An element type incompatible with the other collection can also lead to `ClassCastException`.

Therefore, do not assume "two different generic types cannot share elements so it will always return `true`." The call may go through a lookup with specific type constraints.

Similarly, `disjoint` is not a filter that automatically skips `null`. If you need to treat `null` as a shared element, both inputs must support that query. The demo program uses a list that allows `null` and a `HashSet` that allows `null` so the experiment has valid conditions.

`Collection` allows documented differences regarding invalid elements and query exceptions. [Collection contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

### Two different equality rules can make the result undefined

The `disjoint` documentation states clearly: if one collection uses a non-standard equality check, both must use that same check, otherwise the method's result is undefined.

Examples to watch out for:

- A `SortedSet` using an ordering inconsistent with `equals`, such as case-insensitive string comparison.
- A key set from an `IdentityHashMap`, which uses reference identity instead of `equals`.

Do not write code assuming a mandatory `true`/`false` result when mixing such incompatible semantics. Swapping the two arguments or adding an extra element is not the right fix.

There are two valid approaches: normalize the data to a unified business rule, or ensure both structures actually use the same equivalence relation. "Both have element type `String`" does not prove the two matching relations are the same.

The demo program tests two `TreeSet`s both using `String.CASE_INSENSITIVE_ORDER`, one containing `"red"` and the other containing `"RED"`. They share the same case-insensitive rule, so `disjoint` returns `false`. The program does **not** mix one such set with a set based on `String.equals` and guess the result.

This is a documented contract boundary, not a private optimization specific to one Java version. [disjoint API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#disjoint(java.util.Collection,java.util.Collection)).

### Wanting the list of common elements is a different question

If you need to know the exact overlapping codes to display an error, a boolean is not enough. Perform an intersection operation that matches your equality rules and modification permissions.

Do not call `retainAll` directly on someone else's source just to compute an intersection if you are not allowed to modify the source. If you compute on a copy, you still must preserve element semantics and decide whether duplicates need to be kept.

## 8. Applying these to maps through the right view

Suppose:

~~~java
Map<String, Integer> quantities =
        Map.of("small", 4, "large", 9, "medium", 4);
~~~

A `Map` itself is not a valid input for methods accepting `Collection`. Its views answer different questions:

| View | Example question |
| --- | --- |
| `quantities.keySet()` | Do the keys overlap with another group of keys? |
| `quantities.values()` | What is the largest quantity? How many mappings have value 4? |
| `quantities.entrySet()` | Which mapping has the largest value according to an entry comparator? |

`Collections.max(quantities.values())` returns 9. `frequency(quantities.values(), 4)` returns 2, because two mappings with the same value still contribute two elements to the values view.

If you need to return the winning key as well, simply taking the max of `values` and scanning for the key may not express a tie-breaking rule. You can select an entry using a comparator by value and add a key tie-breaker if needed.

Map views can be backed by the source map. After selecting an entry, you also need to consider the entry's lifecycle contract if you plan to keep it around; do not assume a read query creates an independent snapshot. [Map collection views, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 9. Complete program with exact stdout

Save the code to **`CollectionQueriesDemo.java`**. Numeric data and offers are kept in unmodifiable lists to demonstrate that queries do not require permission to update the container.

When two offers share the lowest cost, the program only asserts the cost value in the selection without a tie-breaker. Specific code selection only appears after adding the code criterion to the comparator.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.TreeSet;

public class CollectionQueriesDemo {
    record Offer(String code, int cost) {
    }

    private static void noElement(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (NoSuchElementException ex) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 2, 7, 2);
        System.out.println("numbers.min=" + Collections.min(numbers));
        System.out.println("numbers.max=" + Collections.max(numbers));
        System.out.println("numbers.minReverse="
                + Collections.min(numbers, Comparator.reverseOrder()));
        System.out.println("numbers.maxReverse="
                + Collections.max(numbers, Comparator.reverseOrder()));
        System.out.println("numbers.after=" + numbers);

        List<Offer> offers = List.of(
                new Offer("B", 50),
                new Offer("A", 50),
                new Offer("C", 80));
        Comparator<Offer> byCost = Comparator.comparingInt(Offer::cost);
        Offer cheapest = Collections.min(offers, byCost);
        System.out.println("offer.minCost=" + cheapest.cost());
        System.out.println("offer.maxCode="
                + Collections.max(offers, byCost).code());
        System.out.println("offer.minWithTieBreak="
                + Collections.min(
                        offers, byCost.thenComparing(Offer::code)).code());
        System.out.println("frequency.offerA="
                + Collections.frequency(offers, new Offer("A", 50)));
        System.out.println("frequency.offerX="
                + Collections.frequency(offers, new Offer("X", 50)));
        int cost50 = 0;
        for (Offer offer : offers) {
            if (offer.cost() == 50) {
                cost50++;
            }
        }
        System.out.println("predicate.cost50=" + cost50);

        List<String> nullable = Arrays.asList("x", null, "x", null);
        System.out.println("frequency.null="
                + Collections.frequency(nullable, null));
        System.out.println("frequency.newString="
                + Collections.frequency(nullable, new String("x")));
        System.out.println("frequency.missing="
                + Collections.frequency(nullable, "missing"));
        Comparator<String> nullLast =
                Comparator.nullsLast(Comparator.naturalOrder());
        System.out.println("nulls.minLast="
                + Collections.min(nullable, nullLast));
        System.out.println("nulls.maxLast="
                + Collections.max(nullable, nullLast));

        TreeSet<Integer> reverseSet =
                new TreeSet<>(Comparator.reverseOrder());
        reverseSet.addAll(List.of(2, 9, 4));
        System.out.println("tree.first=" + reverseSet.first());
        System.out.println("tree.minNatural="
                + Collections.min(reverseSet));
        System.out.println("tree.minOwnComparator="
                + Collections.min(reverseSet, reverseSet.comparator()));

        TreeSet<String> insensitive =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        insensitive.add("red");
        TreeSet<String> sameRule =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        sameRule.add("RED");
        System.out.println("case.containsRED="
                + insensitive.contains("RED"));
        System.out.println("case.frequencyRED="
                + Collections.frequency(insensitive, "RED"));
        System.out.println("case.disjointSameRule="
                + Collections.disjoint(insensitive, sameRule));

        List<String> requested = List.of("READ", "WRITE", "READ");
        Set<String> blocked = Set.of("DELETE", "WRITE");
        System.out.println("disjoint.common="
                + Collections.disjoint(requested, blocked));
        System.out.println("disjoint.separate="
                + Collections.disjoint(requested, Set.of("ARCHIVE")));
        System.out.println("disjoint.empty="
                + Collections.disjoint(
                        Collections.<String>emptyList(), requested));
        System.out.println("disjoint.selfNonempty="
                + Collections.disjoint(requested, requested));
        List<String> empty = Collections.emptyList();
        System.out.println("disjoint.selfEmpty="
                + Collections.disjoint(empty, empty));
        Set<String> containsNull = new HashSet<>();
        containsNull.add(null);
        System.out.println("disjoint.commonNull="
                + Collections.disjoint(nullable, containsNull));

        Map<String, Integer> quantities =
                Map.of("small", 4, "large", 9, "medium", 4);
        System.out.println("map.maxValue="
                + Collections.max(quantities.values()));
        System.out.println("map.frequency4="
                + Collections.frequency(quantities.values(), 4));
        System.out.println("map.keysDisjoint="
                + Collections.disjoint(
                        quantities.keySet(), Set.of("unknown")));

        noElement("empty.min",
                () -> Collections.min(Collections.<Integer>emptyList()));
        noElement("empty.max",
                () -> Collections.max(Collections.<Integer>emptyList()));
        System.out.println("empty.frequency="
                + Collections.frequency(empty, "x"));
        List<Integer> single = List.of(5);
        System.out.println("single.minMax="
                + Collections.min(single) + "/" + Collections.max(single));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 CollectionQueriesDemo.java
java CollectionQueriesDemo
~~~

JDK 17 or later is required for this compile command. The code was compiled with `--release 17` and run on OpenJDK 24.0.2, exiting successfully. Exact stdout:

~~~text
numbers.min=2
numbers.max=9
numbers.minReverse=9
numbers.maxReverse=2
numbers.after=[9, 2, 7, 2]
offer.minCost=50
offer.maxCode=C
offer.minWithTieBreak=A
frequency.offerA=1
frequency.offerX=0
predicate.cost50=2
frequency.null=2
frequency.newString=2
frequency.missing=0
nulls.minLast=x
nulls.maxLast=null
tree.first=9
tree.minNatural=2
tree.minOwnComparator=9
case.containsRED=true
case.frequencyRED=0
case.disjointSameRule=false
disjoint.common=false
disjoint.separate=true
disjoint.empty=true
disjoint.selfNonempty=false
disjoint.selfEmpty=true
disjoint.commonNull=false
map.maxValue=9
map.frequency4=2
map.keysDisjoint=true
empty.min=NoSuchElementException
empty.max=NoSuchElementException
empty.frequency=0
single.minMax=5/5
~~~

### Explaining the output by matching relation

**`numbers`:** natural min is 2, natural max is 9. The reversed comparator makes min 9 and max 2. The list keeps its original order; no sorting is needed to select extrema.

**`offer`:** the lowest cost is 50; the code of the highest-cost offer is C because cost 80 is unique. When a code criterion is added to break ties at the lowest cost, A is selected.

**`frequency.offerA`, `frequency.offerX`, and `predicate.cost50`:** record A/50 appears once; record X/50 does not appear. Yet there are two offers with cost 50. A condition on cost is not the same as full-record `equals`.

**`frequency.null` and `frequency.newString`:** a `null` target is handled meaningfully; a new string with a different reference is still equal to `"x"` and is counted twice.

**`nulls`:** the comparator placing `null` last makes max return `null` on a non-empty collection. This is not a "no result due to empty data" case.

**`tree`:** the first element in the set's descending order is 9; natural min is still 2; min passed the set's own comparator is 9.

**`case`:** `contains("RED")` uses the set's rule and returns `true`, whereas `frequency` uses `String.equals` and returns 0. Both sets in `disjoint` use the same case-insensitive rule, so they share a member under that rule.

**`disjoint`:** sharing `WRITE` yields `false`; the separate `ARCHIVE` group yields `true`. Empty/same-instance boundaries are tested separately. Two collections supporting `null` recognize `null` as a common element.

**`map`:** max over values is 9 and there are two 4s. Checking the key `unknown` against the key set finds no common element.

**`empty` and `single`:** min/max have no element to return so they properly throw `NoSuchElementException`. Frequency on an empty list is 0. With a single element 5, both min and max are 5.

The `noElement` helper causes the program to fail if an empty query unexpectedly does not throw an exception. The program does not rely on exception message text or hash set/map iteration order to produce stdout.

## 10. Cost and choices for repeated queries

### Traversal min/max instead of sorting

Min or max on a typical collection needs a single traversal keeping one candidate. When comparison is constant-time and traversal is linear, the work is `O(n)` with minimal auxiliary state.

Sorting just to get one extremum usually does more work and may also alter the input order if sorted in place. Only sort when you actually need the entire sorted order or a subsequent step uses it.

Calling min and then max is two traversals; the total is still `O(n)` in growth order, not `O(n²)`. If you need multiple statistics simultaneously over an expensive source, consider a suitable single-pass aggregation instead of repeating all queries.

For an already-ordered structure where the query criterion matches the order it maintains, specialized operations like first/last may be more appropriate. Keep the comparator's meaning straight; do not assume `first` of a descending set is the naturally smallest number.

### Simple frequency for a few queries, a count table for many

Each call to `frequency` must inspect elements according to its equality rule. If you query `q` values on a list of `n` elements by calling it separately each time, it can take work on the order of `q × n` checks.

If you need statistics for all values or look up frequencies many times, you can build a count table once:

~~~java
Map<String, Integer> counts = new HashMap<>();
for (String value : values) {
    counts.merge(value, 1, Integer::sum);
}
~~~

This is illustrative code with `List<String> values` and necessary imports. You must maintain a proper `equals`/`hashCode` contract and know the `null` policy of the map used as an index.

`HashMap` supports `null` keys and has constant-time get/put cost under suitable hash dispersion conditions. That is not a guarantee for every `Map` implementation or for a very expensive custom `equals` method. [HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

The count table must also be updated or rebuilt if the source changes. Optimizing queries must not trade away accuracy for stale results that callers assume are still current.

### Disjoint depends on membership-check cost

If membership checking in a list requires a linear scan, comparing two disjoint lists can take work on the order of the product of their sizes. If one side is a `HashSet` with efficient lookup, the check is usually much cheaper.

Building a separate hash set can pay off for multiple queries, but it uses extra memory and must preserve the same equality relation as the problem. Do not convert an identity-based or custom-comparator set into a `HashSet` and think only performance changes.

`HashSet` documents cost conditions for membership operations based on hash dispersion, and does not guarantee iteration order. [HashSet, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

There is no unconditional `O(n + m)` formula for every pair of custom `Collection`s. You must consider traversal, `contains`, `equals`, and the actual input data.

## 11. Common mistakes when combining queries

### Using min/max as if it returns a default number on empty

An empty collection has no extremum element. A default value must be an application API decision; min/max does not make that decision for you.

### Picking an element by comparator then counting with `frequency` to count all tied elements

A min by cost might be A/50. `frequency(offers, selected)` counts records equal to A/50, not all records with cost 50. To count tied candidates, check `comparator.compare(element, selected) == 0` with a valid comparator or check the specific field needed.

### Interpreting `disjoint` as "has intersection"

The method name means having no elements in common. `true` means no overlap; `false` means at least one element in common. Write variable names or explicit negations clearly to avoid inverted branches.

### Counting in a set and using the result to infer counts in the source list

Converting a list to a set can lose duplicate counts according to the set's relation. `frequency(set, x)` cannot recover how many times `x` appeared in the original list. If you want frequency, count on a source that preserves occurrences or use a count table built from that source.

### Assuming read-only queries are atomic snapshots

Min/max/frequency/disjoint do not actively modify the input, but multiple reads do not automatically occur against the same state if the source is updated concurrently.

A "no duplicate codes" result at check time does not guarantee that adding a code immediately afterward will not conflict with another update. If checking and acting must be consistent, you need an appropriate protocol with the owner of the data.

Do not treat the absence of `ConcurrentModificationException` as proof that the source did not change. Collection concurrency contracts and data publication rules must still be respected.

### Assuming element-selection methods return a deep copy

The result of min/max can be the very same object held by the source. If you need to return stable read-only data externally, convert it to an immutable representation or protect the object according to the application's contract.

## 12. Practice with answers

### Exercise 1 — Traverse or sort?

An unmodifiable list contains `[6, 1, 4, 1]`. You need to know the min and max while preserving the list's order.

**Question:** Do you need to create an `ArrayList` and sort it? What are the two results?

**Answer:** No. `Collections.min` returns 1 and `Collections.max` returns 6 without modifying the order. Both `1`s remain. Only create a sorted copy if you need that entire order for another purpose.

### Exercise 2 — Min in descending order

With `[3, 8, 5]`, call `Collections.min(values, Comparator.reverseOrder())`.

**Question:** Is the result 3 or 8? Why doesn't the name `min` automatically imply natural ordering?

**Answer:** The result is 8. In the descending order defined by the comparator, 8 comes before 5 and 3, so it is the minimum under that ordering. If you want the natural minimum, use the no-comparator overload or the natural-order comparator.

### Exercise 3 — Two offers with the same cost

There are `Offer("B", 20)` and `Offer("A", 20)`. The current comparator only compares cost.

**Question:** If a test requires A to be selected, is the contract sufficient? What should you do if the real requirement is lowest cost, then lowest code?

**Answer:** Not sufficient: the current comparator treats both as tied, and the requirement for code A is not expressed. Use `Comparator.comparingInt(Offer::cost).thenComparing(Offer::code)` and then take the min. If you only care about cost, assert that cost equals 20 instead of forcing a specific code.

### Exercise 4 — Counting by object or by field?

A list has A/20, B/20, and A/20, using the `Offer` record from the program.

**Question:** What is the frequency of `new Offer("A", 20)`? What about `new Offer("X", 20)`? How many elements have cost 20?

**Answer:** 2, 0, and 3, respectively. The first two questions use full-record `equals`; the last uses a condition on the cost field. A comparator that only compares cost does not make record X/20 equal to record A/20.

### Exercise 5 — `null` as a result or missing data?

A non-empty list contains `["a", null, "b"]`. Use `Comparator.nullsLast(Comparator.naturalOrder())` to get max.

**Question:** What is max? Can that be treated as proof that the list is empty?

**Answer:** Max is `null` because the comparator places `null` greater than any non-`null` string. The collection is not empty. On an empty collection, min/max throws `NoSuchElementException`; do not conflate the two cases if the model allows `null`.

### Exercise 6 — Reading the boolean of `disjoint`

A is `["x", "x", "y"]`. B is `["z", "y"]`. C is an empty collection.

**Question:** What do `disjoint(A, B)`, `disjoint(A, C)`, and `disjoint(A, A)` return for collections using standard `equals` and compatible elements?

**Answer:** `false`, `true`, and `false`, respectively. `y` is shared between A and B; an empty collection shares no elements with A; A is non-empty so it shares elements with itself. How many times `x` repeats does not change this existence answer.

### Exercise 7 — Case-insensitive set

A `TreeSet` using `String.CASE_INSENSITIVE_ORDER` holds `"red"`. `contains("RED")` returns `true`.

**Question:** Can you infer `frequency(set, "RED") == 1`? Should you mix that set with a hash set using `String.equals` in `disjoint` and enforce a specific boolean result?

**Answer:** No to both inferences. `frequency` uses `Objects.equals`, so it does not count `"red"` as `"RED"`. `disjoint` requires non-standard equality checks to be compatible across both collections; mixing such relations makes the result undefined by contract. Normalize the data or use the exact same rule on both sides.

### Exercise 8 — Repeated frequency queries and changing data

A source has `n` elements, and you need to return frequencies for `q` codes. Each code currently calls `Collections.frequency` separately.

**Question:** What quantity can the work grow with? How can it be improved, and what conditions must be preserved?

**Answer:** It may have to inspect on the order of `q × n` elements. Building a count table in a single pass and then looking up by code can be suitable for many queries. You must preserve proper `equals`/`hashCode`, `null` policies, memory limits, and consistency when the source changes. An un-updated count table is stale data; it no longer automatically represents the current state of the source.

When choosing these utilities, identify the active relation first: ordering to select extrema, `equals` to count, or compatible membership semantics to check overlap. Then handle emptiness, `null`, and source lifecycle explicitly so that a small result accurately reflects the business question.
