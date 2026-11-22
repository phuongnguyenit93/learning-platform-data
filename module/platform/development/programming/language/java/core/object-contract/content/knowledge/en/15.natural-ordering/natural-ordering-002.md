# Natural Ordering: compareTo() Returns Negative Sign, Zero, or Positive Sign

## 1. Exact meaning of the compareTo result

In Java, a class implements **Comparable<T>** when it wants to define a natural ordering for objects of the same type. The compareTo(T other) method returns an int value, yet it is the **sign** of the result that represents the relationship:

| Value of x.compareTo(y) | Meaning | Ascending sort |
| --- | --- | --- |
| Negative, less than 0 | x comes before y | x comes first |
| Equal to 0 | x and y are equivalent in ordering | Same logical position by comparison |
| Positive, greater than 0 | x comes after y | x comes later |

In particular, **compareTo is not required to return exactly -1, 0, or 1**. Values like -25, -4, 7, 25 are all valid when they match the ordering relation. Do not interpret the magnitude of the returned number as the distance between two objects.

Example with String:

~~~java
System.out.println("a".compareTo("z")); // -25
System.out.println("a".compareTo("a")); // 0
System.out.println("z".compareTo("a")); // 25
~~~

With these two simple Latin characters, String.compareTo returns the difference of the first differing UTF-16 character values, yielding negative/positive results with magnitude 25.

Recommended check to use:

~~~java
int result = x.compareTo(y);
if (result < 0) {
    System.out.println("x comes before y");
} else if (result > 0) {
    System.out.println("x comes after y");
} else {
    System.out.println("x is equivalent to y in ordering");
}
~~~

This is an illustrative snippet in a context where compatible x and y have already been declared; it is not a standalone runnable program. **Do not check result == -1 to mean less than**, because results like -2 or -25 carry the same meaning. You can use Integer.signum(result) when normalizing to -1/0/1 is needed, though that is not required for conditional branches.

## 2. Comparable and Comparator both return a sign

`Comparable<T>` places the natural ordering rule inside the data type; `Comparator<T>` defines an ordering that can be passed externally, such as sorting by descending date or by score. Both use **negative/0/positive sign**, so the `result < 0` check applies to both `x.compareTo(y)` and `comparator.compare(x, y)`.

When using `TreeSet` or `TreeMap` with a custom comparator, `0` also determines whether two elements/keys share the same logical position in the tree structure. The first lesson in the chapter thoroughly explains when to choose natural ordering versus a comparator.

## 3. Wrong sign when subtraction overflows

The returned sign is only useful when the comparison computes correctly: `return a - b` with two `int`s can overflow and reverse the relationship direction.

~~~java
int low = Integer.MIN_VALUE;
int high = Integer.MAX_VALUE;
System.out.println(low - high);                  // 1 (wrong sign for comparison)
System.out.println(Integer.compare(low, high)); // -1
~~~

Use `Integer.compare`, `Long.compare`, and corresponding helpers. The lesson on **overflow in compareTo** will examine `MIN_VALUE`/`MAX_VALUE` boundaries, casting `long` to `int`, and the impact on transitivity.

## 4. Java 17+: complete, runnable example

Save as file **CompareToSignDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class CompareToSignDemo {
    public static void main(String[] args) {
        Job first = new Job(3, "B");
        Job second = new Job(3, "A");
        Job third = new Job(1, "A");

        System.out.println("first vs second: " + first.compareTo(second));
        System.out.println("second vs first: " + second.compareTo(first));
        System.out.println("same value: "
                + second.compareTo(new Job(3, "A")));

        List<Job> jobs = new ArrayList<>();
        jobs.add(first);
        jobs.add(second);
        jobs.add(third);
        jobs.sort(null);
        System.out.println("sorted list: " + jobs);

        Set<Job> sortedJobs = new TreeSet<>(jobs);
        System.out.println("TreeSet<Job> size: " + sortedJobs.size());

        int low = Integer.MIN_VALUE;
        int high = Integer.MAX_VALUE;
        System.out.println("subtraction: " + (low - high));
        System.out.println("Integer.compare: " + Integer.compare(low, high));
        System.out.println("String compare z/a: " + "z".compareTo("a"));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("BigDecimal compare: " + a.compareTo(b));
        System.out.println("BigDecimal equals: " + a.equals(b));

        Set<BigDecimal> tree = new TreeSet<>();
        tree.add(a);
        tree.add(b);
        Set<BigDecimal> hash = new HashSet<>();
        hash.add(a);
        hash.add(b);
        System.out.println("TreeSet<BigDecimal> size: " + tree.size());
        System.out.println("HashSet<BigDecimal> size: " + hash.size());
    }

    record Job(int priority, String code) implements Comparable<Job> {
        Job {
            Objects.requireNonNull(code);
        }

        @Override
        public int compareTo(Job other) {
            Objects.requireNonNull(other);
            int byPriority = Integer.compare(priority, other.priority);
            if (byPriority != 0) {
                return byPriority;
            }
            return code.compareTo(other.code);
        }
    }
}
~~~

Run commands from the directory containing the file:

~~~bash
javac -encoding UTF-8 CompareToSignDemo.java
java CompareToSignDemo
~~~

Stdout result:

~~~text
first vs second: 1
second vs first: -1
same value: 0
sorted list: [Job[priority=1, code=A], Job[priority=3, code=A], Job[priority=3, code=B]]
TreeSet<Job> size: 3
subtraction: 1
Integer.compare: -1
String compare z/a: 25
BigDecimal compare: 0
BigDecimal equals: false
TreeSet<BigDecimal> size: 1
HashSet<BigDecimal> size: 2
~~~

**Explanation:** first and second both have priority 3, and code "B" comes after "A", so compareTo is positive. When reversed, the result is negative. Two Jobs with the same priority and code return 0. After sorting, the Job with priority 1 comes first; the Jobs with priority 3 are ordered by code A then B. Record Job has equals/hashCode generated from both components, matching the pair of fields that compareTo uses.

The two extreme integers show that overflowing subtraction returns 1 while Integer.compare returns -1. "z".compareTo("a") returns 25, proving compareTo is not limited to -1/0/1. Two BigDecimals representing the same value with different scales lead to a difference between compareTo and equals, analyzed in the next section.

## 5. Interpreting the sign properly across the entire contract

Beyond negative/0/positive sign, a valid `compareTo` also preserves the following properties over the domain of comparable objects:

| Rule | What to check |
| --- | --- |
| Sign reversal | `Integer.signum(x.compareTo(y)) == -Integer.signum(y.compareTo(x))` |
| Transitivity | If `x > y` and `y > z` then `x > z` |
| Equivalent values | If `x.compareTo(y) == 0`, the signs when comparing `x` and `y` against any valid `z` must be identical |
| `null` | `x.compareTo(null)` throws `NullPointerException` |

The sign-reversal rule speaks only of **sign**, not requiring the two results to have the same absolute value. For example, `-3` and `8` are still validly opposite in sign if the other properties also hold. Subsequent lessons test each condition with concrete pairs and triples.

## 6. Sign 0 means equivalent in ordering, not automatically equals

`compareTo == 0` determines that two values have the **same position in ordering**. `equals == true` is logical object equality. Java strongly recommends that these two relations be consistent, yet permits intentional differences.

For example, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` while `equals` returns `false` due to differing `scale`. Therefore `TreeSet<BigDecimal>` retains only one ordering-equivalent element, whereas `HashSet<BigDecimal>` retains two elements based on `equals/hashCode`. The program in section 4 observes this exact difference; the later lesson on `equals` and `compareTo` guides choosing the right contract.

## 7. Multi-field comparison: breaking ties properly

Standard pattern for comparing by the first field, then the second field:

~~~java
// Excerpt in class Person having non-null String lastName, firstName.
@Override
public int compareTo(Person other) {
    int byLast = lastName.compareTo(other.lastName);
    if (byLast != 0) {
        return byLast;
    }
    return firstName.compareTo(other.firstName);
}
~~~

If the earlier key comparison returns **any non-zero value**, return it immediately; only compare the next key when equal to 0. Do not check byLast == -1 or byLast == 1. If a field can be null, use Comparator.nullsFirst/nullsLast or handle it explicitly, avoiding calling compareTo directly on null.

An alternative Comparator can be written as:

~~~java
// Illustration in a context with class Person and import java.util.Comparator.
Comparator<Person> byName =
        Comparator.comparing(Person::lastName)
                  .thenComparing(Person::firstName);
~~~

For primitive integers, Comparator.comparingInt and comparingLong make code concise and avoid unnecessary boxing. If the comparator is used in TreeSet/TreeMap, consider the impact of compare == 0 on key distinction.

## 8. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking compareTo may only return -1/0/1 | The contract only requires sign | Check < 0, == 0, > 0 |
| Using == -1 to detect coming before | Misses -2, -25, ... | Check < 0 |
| Taking the difference of two ints or longs | Can overflow | Integer.compare, Long.compare |
| Casting a long difference to int | Can lose information and invert sign | Long.compare |
| Treating compareTo magnitude as distance | compareTo expresses order, not a metric | Define a separate metric |
| Assuming compareTo == 0 always implies equals | False for BigDecimal | Check the type's contract |
| Comparing only one non-distinguishing key | TreeSet may merge distinct values | Add tie-breaker keys if needed |
| Lacking symmetry or transitivity | Sorting and collections may fail expectations | Test the ordering relation |
| Calling compareTo on a null field | Can throw NullPointerException | Explicit null policy |
| Assuming < on float/double is always enough | Does not handle NaN and signed zero per wrapper | Float.compare/Double.compare when appropriate |

## 9. Checklist and testing

- **Sign:** less returns negative, equal in ordering returns 0, greater returns positive.
- **Sign reversal:** swapping x/y must invert the sign.
- **Self-comparison:** x.compareTo(x) == 0.
- **Transitivity:** triples x, y, z must maintain consistent order.
- **Equivalence:** if x.compareTo(y) == 0, signs when compared to the same z must match.
- **Numeric boundaries:** test Integer.MIN_VALUE, Integer.MAX_VALUE, and extreme longs.
- **Tie-breaking:** matching earlier fields must be compared by subsequent fields.
- **Null:** verify the intended null-handling policy.
- **Collections:** test List.sort, TreeSet/TreeMap with equivalent keys.
- **Equals:** if the class documentation states ordering is compatible with equals, verify compareTo == 0 **if and only if** equals is true.

Short assertion snippet placed in a context where three objects a, b, c are already declared:

~~~java
if (a.compareTo(b) >= 0) {
    throw new AssertionError("a must come before b");
}
if (b.compareTo(a) <= 0) {
    throw new AssertionError("b must come after a");
}
if (c.compareTo(c) != 0) {
    throw new AssertionError("Self-comparison must return 0");
}
~~~

These assertions are illustrative snippets, not a standalone program; test data must be chosen according to the class's comparison rules.

## 10. Key takeaways

- **Negative:** current object comes before the argument.
- **Zero:** both objects are equivalent in ordering.
- **Positive:** current object comes after the argument.

What to remember is the **sign of compareTo**, not its magnitude. Use standard comparison methods instead of subtraction, adhere to sign symmetry and transitivity, handle multiple keys properly, and clearly understand the relationship between compareTo == 0 and equals when working with TreeSet/TreeMap.