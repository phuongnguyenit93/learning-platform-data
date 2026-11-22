# Two Values with `compareTo() == 0` Must Compare Consistently Against a Third Value

## 1. The rule of natural ordering in Java

In Java, a class implementing `Comparable<T>` defines **natural ordering** via the method `int compareTo(T other)`. The method returns an integer:

- **Negative** if the current object comes before `other`.
- **`0`** if the two values are considered equivalent under **natural ordering**.
- **Positive** if the current object comes after `other`.

Return values are not required to be `-1`, `0`, `1`; only the **sign** matters to the contract. For instance, `String.compareTo` can return a negative or positive number with an absolute value greater than `1`.

Key point of this lesson: If `x.compareTo(y) == 0`, then **for every valid comparable `z`**, the signs of `x.compareTo(z)` and `y.compareTo(z)` must be the same. That is, a third object must never see `x` coming before it while `y` comes after it.

Written precisely in notation:

```text
x.compareTo(y) == 0
    => signum(x.compareTo(z)) == signum(y.compareTo(z))
       for all z in the same valid comparison domain
```

`signum(n)` is the sign of `n`: negative becomes `-1`, zero becomes `0`, positive becomes `1`. In Java, use `Integer.signum(n)` to check it. The contract **does not require** `x.compareTo(z)` to equal the exact integer returned by `y.compareTo(z)`, only that the two returned values have the **same sign**.

This rule is also called **substitutability of ordering-equivalent values**: once `x` and `y` are treated as occupying the same position in ordering, we must be able to use them interchangeably in any comparison with `z`.

## 2. Why is consistent comparison against a third value required?

Imagine having three values `x`, `y`, `z`:

```text
x.compareTo(y) == 0    // x and y are placed at the same position
x.compareTo(z) < 0     // x comes before z
y.compareTo(z) > 0     // y comes after z
```

The three conclusions above are **contradictory**: if `x` and `y` are equivalent in ordering, they cannot simultaneously lie on opposite sides of `z`. Sorting algorithms, binary search, balanced trees (`TreeSet`, `TreeMap`), and ordered structures rely on the assumption that comparisons form a valid order.

Failing to obey this can make results depend on the algorithm's execution path: a newly inserted value becomes hard to find, `contains()` produces surprising results, or complex sort operations fail due to a violated comparison contract. Do not try to predict a specific `TreeSet` order when the `compareTo` implementation is already broken.

## 3. Related requirements of `Comparable`

The third-value rule belongs to a broader contract. For `x`, `y`, `z` in the same valid comparison domain:

**Sign symmetry:**

```text
signum(x.compareTo(y)) == -signum(y.compareTo(x))
```

**Transitivity:** If `x > y` and `y > z` under `compareTo`, then `x > z`; similarly for the less-than side.

```text
x.compareTo(y) > 0  &&  y.compareTo(z) > 0
    => x.compareTo(z) > 0
```

**Equivalence-class consistency with a third value:**

```text
x.compareTo(y) == 0
    => signum(x.compareTo(z)) == signum(y.compareTo(z))
```

From these properties, the `compareTo() == 0` relation acts as an **equivalence relation** in ordering: members of the same group cannot be separated in position by a third value.

Do not use `return this.score - other.score` to implement integer comparison: subtraction can **overflow**, flipping the sign and breaking the contract. Use `Integer.compare(this.score, other.score)` (and similarly `Long.compare`, `Double.compare` when appropriate).

## 4. Bad example: treating equal names as equal while comparing different names by age

Suppose class `BadPerson` writes `compareTo` as follows:

```java
@Override
public int compareTo(BadPerson other) {
    if (name.equals(other.name)) {
        return 0;
    }
    return Integer.compare(age, other.age);
}
```

This is **an illustrative method inside a class** with fields `name` and `age`; it is not a standalone program. The intent sounds reasonable: same name means equal, different names get sorted by age. Yet the two-branch criterion fails to produce a consistent order.

Consider three people:

- `x = ("An", 20)`
- `y = ("An", 30)`
- `z = ("Binh", 25)`

Comparison results:

| Comparison | Result | Reason |
| --- | --- | --- |
| `x.compareTo(y)` | `0` | Same name `"An"` |
| `x.compareTo(z)` | `-1` | Different name and `20 < 25` |
| `y.compareTo(z)` | `1` | Different name and `30 > 25` |

Because `x` and `y` compared to `0`, both **must have the same sign when compared against `z`**. One gives `-1`, the other `1`: this is a contract bug, **even though each individual comparison looks plausible**. The root bug is that the condition identifying "equivalence" uses name, while the relative ordering against others uses age.

## 5. Two ways to fix depending on the goal

**Option A — wanting people with the same name treated as one group in ordering:** Compare **only by name** in every case:

```java
@Override
public int compareTo(BadPerson other) {
    return name.compareTo(other.name);
}
```

Now `("An", 20)` and `("An", 30)` both yield `0`, and when compared against `("Binh", 25)`, both have a negative sign. The third-element condition is preserved. However, if the class's `equals()` still checks age, then this approach can be **inconsistent with `equals()`** — see section 7.

**Option B — wanting to distinguish both name and age:** Use a uniform composite ordering: compare name first; if names are equal, compare age.

```java
@Override
public int compareTo(GoodPerson other) {
    int byName = name.compareTo(other.name);
    if (byName != 0) {
        return byName;
    }
    return Integer.compare(age, other.age);
}
```

Then `("An", 20)` and `("An", 30)` **no longer** compare to `0`, because their ages differ. If two objects have the same name **and** the same age, they compare to `0` and give the same sign against any third person. This is also the approach expressed by `Comparator.comparing(Person::name).thenComparingInt(Person::age)`.

## 6. Complete Java 17+ program

Save the following code to `CompareToThirdDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class CompareToThirdDemo {
    record BadPerson(String name, int age)
            implements Comparable<BadPerson> {
        @Override
        public int compareTo(BadPerson other) {
            if (name.equals(other.name)) return 0;
            return Integer.compare(age, other.age);
        }
    }

    record GoodPerson(String name, int age)
            implements Comparable<GoodPerson> {
        @Override
        public int compareTo(GoodPerson other) {
            int byName = name.compareTo(other.name);
            return byName != 0
                    ? byName
                    : Integer.compare(age, other.age);
        }
    }

    public static void main(String[] args) {
        BadPerson x = new BadPerson("An", 20);
        BadPerson y = new BadPerson("An", 30);
        BadPerson z = new BadPerson("Binh", 25);

        System.out.println("bad x-y: "
                + Integer.signum(x.compareTo(y)));
        System.out.println("bad x-z: "
                + Integer.signum(x.compareTo(z)));
        System.out.println("bad y-z: "
                + Integer.signum(y.compareTo(z)));
        System.out.println("bad third consistency: "
                + (Integer.signum(x.compareTo(z))
                == Integer.signum(y.compareTo(z))));

        GoodPerson a = new GoodPerson("An", 20);
        GoodPerson b = new GoodPerson("An", 20);
        GoodPerson c = new GoodPerson("Binh", 25);
        System.out.println("good a-b: "
                + Integer.signum(a.compareTo(b)));
        System.out.println("good a-c: "
                + Integer.signum(a.compareTo(c)));
        System.out.println("good b-c: "
                + Integer.signum(b.compareTo(c)));
        System.out.println("good equals: " + a.equals(b));

        BigDecimal p = new BigDecimal("2.0");
        BigDecimal q = new BigDecimal("2.00");
        BigDecimal r = new BigDecimal("3.0");
        System.out.println("decimal p-q: " + p.compareTo(q));
        System.out.println("decimal p.equals(q): " + p.equals(q));
        System.out.println("decimal p-r sign: "
                + Integer.signum(p.compareTo(r)));
        System.out.println("decimal q-r sign: "
                + Integer.signum(q.compareTo(r)));

        Set<BigDecimal> ordered = new TreeSet<>();
        ordered.add(p);
        ordered.add(q);
        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(p);
        hashed.add(q);
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("HashSet size: " + hashed.size());
    }
}
```

Run in the directory containing the file with JDK 17 or newer:

```bash
javac CompareToThirdDemo.java
java CompareToThirdDemo
```

Output:

```text
bad x-y: 0
bad x-z: -1
bad y-z: 1
bad third consistency: false
good a-b: 0
good a-c: -1
good b-c: -1
good equals: true
decimal p-q: 0
decimal p.equals(q): false
decimal p-r sign: -1
decimal q-r sign: -1
TreeSet size: 1
HashSet size: 2
```

In `BadPerson`, the comparison returns `0`, yet the two signs when compared to `z` differ. In `GoodPerson`, objects matching in both name and age are considered equivalent by `compareTo` and also equal by `record.equals()`. When compared to `c`, both signs are `-1`; the algorithm is consistent.

`BigDecimal` in the example both satisfies **the third-value comparison rule** (`2.0` and `2.00` are both less than `3.0`) and serves as an important case of **difference between `compareTo()` and `equals()`**.

## 7. Versus equals: two requirements with different strictness

**Mandatory per `Comparable`:** if `x.compareTo(y) == 0`, every valid `z` must receive the **same sign** from `x.compareTo(z)` and `y.compareTo(z)`. This is the condition illustrated by `BadPerson` and `GoodPerson`.

**Strongly recommended:** `x.compareTo(y) == 0` should be equivalent to `x.equals(y)`. `BigDecimal("2.0")` and `BigDecimal("2.00")` have `compareTo == 0` and `equals == false`, yet both still have the same sign when compared against `3.0`. Therefore, inconsistency with `equals` by itself does **not** violate the mandatory third-value rule. The next lesson examines the risks of this inconsistency in `TreeSet` and `TreeMap`.

## 8. Practical consequences for `TreeSet`, `TreeMap`, sorting, and searching

With `TreeSet`/`TreeMap`, the comparison of `Comparable` (or a provided `Comparator`) serves both **ordering** and locating a key:

- If two keys compare to `0`, the tree structure treats them as the same key by ordering; `TreeMap.put()` may update the value attached to the equivalent key, while `TreeSet.add()` may not add the second element.
- If the comparison is non-transitive or violates the third-value rule, the tree structure can exhibit unexpected query behavior because navigation relies on contradictory comparisons.
- If the ordering is inconsistent with `equals()`, `TreeSet` and `HashSet` may evaluate different element counts even when using the same objects.
- Sorting algorithms (`Collections.sort`, `List.sort`, `Arrays.sort`) demand a contract-compliant ordering relation; violations can make results unreliable or throw `IllegalArgumentException` in some cases.

Do not test the correctness of `compareTo` merely by running `TreeSet` on a few elements and observing the output: the algorithm might happen not to traverse a contradictory case. **Directly verify the contract** on representative triples of values.

## 9. How to design and test `compareTo()`

1. **Define the criterion for returning `0`.** For example: same identifier, or same name and age? Objects with `compareTo == 0` must be completely substitutable in subsequent comparisons.
2. **Choose a fixed criterion order.** If comparing by name then age, make name the first criterion; only check age when names are equal. Never switch back and forth between the two criteria depending on the pair being compared.
3. **Use built-in comparison methods.** Choose `Integer.compare`, `Long.compare`, `String.compareTo`, `Comparator.comparing(...).thenComparing(...)`; avoid subtracting integers manually or handling signs by hand when unnecessary.
4. **Standardize `null` semantics.** `Comparable.compareTo(null)` must normally throw `NullPointerException`; if using `Comparator`, you can explicitly choose `Comparator.nullsFirst(...)`/`nullsLast(...)` where `null` needs support.
5. **Prefer consistency with `equals()` when designing value classes**, especially if the same object serves as a key for both hash collections and sorted collections.
6. **Test triples of values.** For every test triple `(x, y, z)` where `x.compareTo(y) == 0`, confirm `Integer.signum(x.compareTo(z)) == Integer.signum(y.compareTo(z))`. Also verify sign symmetry and transitivity.

Simplified check example inside a Java method:

```java
static <T extends Comparable<? super T>> boolean samePositionToThird(
        T x, T y, T z) {
    return x.compareTo(y) != 0
            || Integer.signum(x.compareTo(z))
                    == Integer.signum(y.compareTo(z));
}
```

The method above **checks the condition only for a single input triple**; it does not prove the contract holds for *all* possible values. The expression `x.compareTo(y) != 0` makes the condition logically true when the premise is unmet. You need boundary data (duplicate values, distinct values, integer extremes, secondary criteria, Unicode strings, etc.) along with transitivity and symmetry checks.

## 10. Common misconceptions

| Misconception | Correct explanation |
| --- | --- |
| `compareTo()` can only return `-1`, `0`, `1` | Results can be any `int`; rules use the **sign** |
| `x.compareTo(y) == 0` only means the pair `x`, `y` happens to be equal | It also requires **the same comparison sign against every `z`** |
| Same name returns `0`, different names compare age is reasonable | Creates contradictory ordering when two people share a name but differ in age |
| `compareTo == 0` always mandates `equals() == true` | Consistency with `equals()` is strongly recommended, not strictly mandatory (e.g. `BigDecimal`) |
| `TreeSet` always uses `equals()` to deduplicate | It uses `compareTo` or `Comparator` to determine equivalent position |
| You can `return a - b` for all integers | Subtraction can overflow and flip the sign; use `Integer.compare(a, b)` |
| Testing ordering of two elements is enough | Must also check the relation to a **third element**, transitivity, and symmetry |

## 11. Self-check

1. If `x.compareTo(y) == 0`, `x.compareTo(z) == -7`, and `y.compareTo(z) == -1`, is there a violation? **No**, because both are negative.
2. If `x.compareTo(y) == 0`, `x.compareTo(z) < 0`, yet `y.compareTo(z) > 0`, is it valid? **No**, because they contradict each other regarding the position of `z`.
3. If `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` yet `equals()` is `false`, does that automatically violate the third-value rule? **No**. `BigDecimal`'s `compareTo` still places both in the same relative position against every number `z`.
4. Why is comparing name first, then age if names are equal, better than returning `0` on equal names and comparing age otherwise? **Because criteria are always applied in a uniform order, enabling a valid ordering definition.**

**Remember:** `compareTo(x, y) == 0` (written as an instance method call `x.compareTo(y) == 0`) forms an **ordering-equivalence** group. Every member of the group must compare against any third value `z` with **the exact same sign**. This is a mandatory requirement of the `Comparable` contract, independent of the recommendation that `compareTo() == 0` should be consistent with `equals()`.