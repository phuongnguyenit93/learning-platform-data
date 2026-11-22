# Objects.compare() with a provided Comparator in Java

## 1. Purpose and meaning

**java.util.Objects.compare(T a, T b, Comparator<? super T> c)** is a static method for comparing two references using a **caller-provided Comparator**. This utility is useful when a type has multiple ways of ordering: by name, by priority, by time, or by multiple combined fields.

Basic rules:

- If a and b **are the same reference** (a == b), Objects.compare returns **0** immediately, without calling the Comparator.
- If a and b **are two different references**, the result is **c.compare(a, b)**, decided by the Comparator.
- The sign of the returned int expresses order: **negative** means a comes before b, **0** means equivalent under the Comparator, **positive** means a comes after b.
- The passed Comparator **does not have to be the natural ordering** of the object type. The caller chooses the comparison policy.

Under the Comparator contract, it is not required to return only -1, 0, or 1; any int with the appropriate sign is valid. Therefore, check result < 0, result == 0, and result > 0 when handling the result.

## 2. API signature and execution mechanism

General Java signature:

~~~java
public static <T> int compare(
        T a,
        T b,
        Comparator<? super T> c)
~~~

Way to picture the behavior, equivalent to the API logic:

~~~java
// Mechanism simulation snippet, not a standalone method to paste into a class.
return (a == b) ? 0 : c.compare(a, b);
~~~

The a == b check **compares reference identity**, without calling a.equals(b). This creates a notable distinction: two objects with equal value under equals yet **different references** are still forwarded to the Comparator.

Example:

~~~java
String x = new String("java");
String y = new String("java");

// x.equals(y) is true, yet x == y is false.
// String.CASE_INSENSITIVE_ORDER is still called:
int result = Objects.compare(x, y, String.CASE_INSENSITIVE_ORDER);
~~~

The result is 0 because the Comparator treats the two strings as equal case-insensitively. In this example, the 0 result comes from the Comparator, **not** from the a == b optimization branch.

Both java.util.Objects and java.util.Comparator must be imported for the isolated snippets in this section.

### Role of the type parameters

- T is the type of the two values being compared.
- Comparator<? super T> allows using a Comparator for T or an appropriate supertype.
- The method returns an int; this integer expresses only **the comparison sign**, not a distance metric.
- When multiple sorting rules are needed for one kind of object, pass different Comparators to the same Objects.compare method.

## 3. Comparing same reference vs. different references

Consider three scenarios:

| Two arguments | Execution branch | Result |
| --- | --- | --- |
| a and b point to the exact same object | Does not call c.compare | Returns 0 |
| a and b are two separate objects, even if a.equals(b) is true | Calls c.compare(a, b) | Depends on the Comparator |
| a and b are two separate objects, a.equals(b) is false | Calls c.compare(a, b) | Depends on the Comparator |

Returning 0 on identical references represents a sensible optimization for a contract-compliant Comparator: an object cannot come before or after itself.

However, **Objects.compare cannot fix a contract-violating Comparator**. If a Comparator is random, non-transitive, or returns contradictory results for different pairs, Objects.compare simply forwards that wrong result back to the caller. Skipping the Comparator call on identical references also means side effects or counters inside the Comparator do not execute in that case. An ideal Comparator should be pure and independent of how many times it is called.

**Difference from Objects.equals:** Objects.equals(a, b) checks equality via Object.equals in a null-safe manner; Objects.compare(a, b, c) determines **ordering under the provided Comparator**. Having compare == 0 does not automatically mean equals == true.

## 4. Null cases: understanding handling boundaries

Objects.compare has one special case:

~~~java
Objects.compare(null, null, comparator); // 0
~~~

When both arguments are null, they share the same reference, so the method returns 0 immediately, **without calling the Comparator**.

However, with exactly one null argument:

~~~java
Objects.compare(null, item, comparator);
Objects.compare(item, null, comparator);
~~~

Here a != b and the Comparator is invoked with a null argument. Objects.compare **does not automatically decide whether null comes first or last**, nor does it guarantee null is supported. If the Comparator does not accept null, it may throw NullPointerException.

How to explicitly set a null policy:

~~~java
// null before any non-null value:
Comparator<String> nullFirst =
        Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER);

// null after any non-null value:
Comparator<String> nullLast =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER);

int firstResult = Objects.compare(null, "A", nullFirst); // -1
int lastResult = Objects.compare(null, "A", nullLast);   // 1
int bothNull = Objects.compare(null, null, nullFirst);   // 0
~~~

These illustrative results -1, 1, 0 are deterministic for standard Comparator.nullsFirst/nullsLast; in general, you should still rely on the sign.

If c = null is passed, **do not treat it as a mechanism to select natural ordering**. With two different references, the method will attempt to call c.compare and throw NullPointerException. With two identical references, the return-0 branch may avoid touching c, but that is not a meaningful substitute for a Comparator.

## 5. Java 17+: full program and output

Save into **`ObjectsCompareDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ObjectsCompareDemo {
    record Ticket(int priority, String code) {
        Ticket {
            Objects.requireNonNull(code);
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket(1, "A");
        Ticket second = new Ticket(2, "B");
        Ticket sameValue = new Ticket(1, "A");

        Comparator<Ticket> byPriorityThenCode =
                Comparator.comparingInt(Ticket::priority)
                          .thenComparing(Ticket::code);

        System.out.println("same reference: "
                + Objects.compare(first, first, byPriorityThenCode));
        System.out.println("first before second: "
                + Objects.compare(first, second, byPriorityThenCode));
        System.out.println("second after first: "
                + Objects.compare(second, first, byPriorityThenCode));
        System.out.println("same value is same reference: "
                + (first == sameValue));
        System.out.println("same value equals: "
                + first.equals(sameValue));
        System.out.println("same value comparison: "
                + Objects.compare(first, sameValue, byPriorityThenCode));

        Ticket laterCode = new Ticket(1, "Z");
        System.out.println("same priority, code Z vs A: "
                + Objects.compare(laterCode, first, byPriorityThenCode));

        Comparator<Ticket> byPriorityOnly =
                Comparator.comparingInt(Ticket::priority);
        System.out.println("priority only comparison: "
                + Objects.compare(first, laterCode, byPriorityOnly));
        System.out.println("different tickets equals: "
                + first.equals(laterCode));

        System.out.println("both null: "
                + Objects.compare(null, null, byPriorityThenCode));
        System.out.println("nullsFirst: "
                + Objects.compare(null, first,
                        Comparator.nullsFirst(byPriorityThenCode)));
        System.out.println("nullsLast: "
                + Objects.compare(null, first,
                        Comparator.nullsLast(byPriorityThenCode)));
        System.out.println("reversed: "
                + Objects.compare(first, second,
                        byPriorityThenCode.reversed()));

        List<Ticket> tickets = new ArrayList<>(List.of(second, first));
        tickets.sort(byPriorityThenCode);
        System.out.println("sorted: " + tickets);

        AtomicInteger callCount = new AtomicInteger();
        Comparator<Ticket> countingComparator = (left, right) -> {
            callCount.incrementAndGet();
            return byPriorityThenCode.compare(left, right);
        };
        Objects.compare(first, first, countingComparator);
        System.out.println("calls after same reference: "
                + callCount.get());
        Objects.compare(first, sameValue, countingComparator);
        System.out.println("calls after different reference: "
                + callCount.get());
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac -encoding UTF-8 ObjectsCompareDemo.java
java ObjectsCompareDemo
~~~

Exact stdout:

~~~text
same reference: 0
first before second: -1
second after first: 1
same value is same reference: false
same value equals: true
same value comparison: 0
same priority, code Z vs A: 25
priority only comparison: 0
different tickets equals: false
both null: 0
nullsFirst: -1
nullsLast: 1
reversed: 1
sorted: [Ticket[priority=1, code=A], Ticket[priority=2, code=B]]
calls after same reference: 0
calls after different reference: 1
~~~

**Reading the output:**

1. References first/first point to the same object, so Objects.compare returns 0. References first/sameValue are different objects, even though record equals is true, so the Comparator still must be called; the result 0 comes from having the same priority and code.
2. The Comparator by priority then code returns negative when first comes before second, and positive in the reverse direction. With equal priority, String.compareTo between "Z" and "A" returns 25: proving it is not restricted to -1/0/1.
3. byPriorityOnly returns 0 for first and laterCode because they share the same priority, while the two records have different codes so equals is false. A Comparator defines **ordering equivalence**, not automatically equality across all attributes.
4. null/null returns 0; nullsFirst and nullsLast create explicit null policies. Reversing the Comparator makes first come after second in the opposite order.
5. The list is sorted ascending by the Comparator from low priority to high.
6. CountingComparator is a call-observation tool: for first/first, count stays 0; for first/sameValue, count increments to 1 even though equals is true. In business code, avoid letting comparison logic depend on such counters/side effects.

## 6. The provided Comparator determines ordering equivalence

Suppose two Tickets have the same priority = 1 yet different codes:

- With Comparator.comparingInt(Ticket::priority), compare returns 0: they are **equivalent when ordered by priority**.
- With Comparator.comparingInt(...).thenComparing(Ticket::code), compare is non-zero: code acts as a tie-breaker.
- Record Ticket's Object.equals uses both priority and code, so two Tickets with different codes are not equal under equals.

This matters in collections:

**List.sort(comparator)** sorts the list using the Comparator and **does not remove** elements whose compare == 0.

**TreeSet(comparator)** or **TreeMap(comparator)** uses compare == 0 to determine whether two keys are equivalent, so a priority-only Comparator can collapse two Tickets with different codes into a single key.

**HashSet** and **HashMap** use equals/hashCode; with the same priority yet different codes, the two Ticket records are two distinct values.

If using a custom Comparator for TreeSet/TreeMap, decide whether compare == 0 is expected to match equals. A valid Comparator can still be inconsistent with equals; consequently, how an ordered collection recognizes keys can differ from a hash-based collection.

## 7. Combining multiple keys and sort directions

Comparator factories make it easy to pass a clear rule into Objects.compare:

~~~java
Comparator<Ticket> ascending =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::code);

Comparator<Ticket> descending = ascending.reversed();

int result = Objects.compare(a, b, descending);
~~~

This snippet is placed in a context that has the Ticket type and objects a and b, not a standalone program. ascending compares priority ascending then code ascending. descending reverses the entire comparison result; if you only want priority reversed while keeping code ascending, combine each criterion as desired.

Example when comparing Strings:

~~~java
int caseSensitive =
        Objects.compare("java", "JAVA", Comparator.naturalOrder());
int ignoreCase =
        Objects.compare("java", "JAVA", String.CASE_INSENSITIVE_ORDER);
~~~

caseSensitive is **positive** because lowercase characters come after uppercase characters in String order; ignoreCase is **0**. This does not mean default String.equals treats "java" and "JAVA" as equal; these are two relations produced by two different Comparators.

When a key field is numeric, prefer Comparator.comparingInt, comparingLong, comparingDouble, or Integer.compare/Long.compare. Do not manually compute a difference to decide ordering because subtraction can overflow, especially with extreme int/long values.

## 8. The Comparator contract must still be upheld

Objects.compare **does not validate** that a Comparator is valid. The Comparator you provide must still satisfy the requirements:

1. **Sign symmetry:** the sign of compare(a, b) must be the opposite sign of compare(b, a).
2. **Transitivity:** if a > b and b > c, then a > c.
3. **Stability of equivalence classes:** if compare(a, b) == 0, comparing a against z and b against z must yield **the same result sign**.
4. **Stable comparison data:** results must not fluctuate with time, randomness, or counters when the compared information has not changed.
5. **Clear null rules:** if the Comparator supports null, it must apply them consistently and satisfy all conditions above.

In particular, do not write a Comparator that only checks sign via a.priority - b.priority when fields are int; subtraction can overflow and invert the relation. Use Integer.compare or Comparator.comparingInt.

When a Comparator is inconsistent with Object.equals, this may be an intentional choice to group by one field; however, understand the impact on sorted collections and never claim compare == 0 automatically implies equals true.

## 9. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking Objects.compare automatically uses natural ordering | Missing Comparator and misunderstood behavior | Always supply an appropriate Comparator |
| Thinking Objects.compare uses a.equals(b) to skip comparison | Two objects with equals true yet different references still go through the Comparator | Remember the optimization branch is a == b |
| Passing a non-null-safe Comparator when one argument is null | May throw NullPointerException | Use Comparator.nullsFirst/nullsLast |
| Assuming Objects.compare(null, null, c) calls c.compare | Actually returns 0 early | Do not rely on Comparator side effects |
| Treating compare == 0 as equals true | Wrong if the Comparator inspects only part of the data | Separate ordering relation from equals |
| Checking result == -1 or result == 1 | Can miss values like -25 or 25 | Check sign result < 0 / > 0 |
| Using int/long subtraction inside a comparator | Overflow and sign inversion | Integer.compare/Long.compare |
| Comparator changes with external state | Sort and TreeSet/TreeMap cannot guarantee stability | Pure Comparator, stable key data |
| Using Objects.compare to replace Objects.equals | Compares ordering instead of equality | Use the right API for the goal |

Note: Objects.compare returns 0 on identical references even if the Comparator is written abnormally; do not exploit that behavior to dodge bugs in a contract-violating Comparator. Fix the Comparator so the comparison relation is consistent across all valid pairs.

## 10. Meaningful testing

To test Objects.compare usage, check:

- **Same reference:** Objects.compare(x, x, c) returns 0.
- **Different references with same value:** the Comparator is invoked and produces the right result, typically 0 if the policy checks the same attributes.
- **Less than / greater than:** verify negative or positive sign in both directions, without forcing exact -1/1.
- **Equal on secondary criterion:** same priority yet different code; test a priority-only comparator and a comparator with a tie-breaker key.
- **One/both null:** with a null-supporting Comparator, verify ordering; with a non-null-supporting Comparator, verify the failure matches the application contract.
- **Reversal:** reversed flips the sign for non-equivalent pairs.
- **Collections:** List.sort preserves all elements; TreeSet may merge on compare == 0.
- **Stability:** with unchanged comparison data, repeated calls should keep equivalent results.

Assertion example in a context having objects x, y and Comparator c:

~~~java
int forward = Objects.compare(x, y, c);
int backward = Objects.compare(y, x, c);
if (Integer.signum(forward) != -Integer.signum(backward)) {
    throw new AssertionError("Comparison sign is not symmetric");
}
~~~

This snippet illustrates a check, not a standalone program; testing transitivity requires adding a third object and appropriate data. Do not compare forward == -backward using raw arithmetic negation because Integer.MIN_VALUE cannot be safely negated under int arithmetic; Integer.signum lets you examine only the sign.

## 11. When to use and when not to?

**Use** Objects.compare when you want a concise utility to compare two references with an explicit Comparator, especially if you want the fast return-0 branch for identical references, or if the codebase consistently uses java.util.Objects utilities.

**You can call directly** c.compare(a, b) if the policy is clear and you want every comparison to go through the Comparator; the two call styles can differ in the same-reference case and Comparator side effects. An ordinary valid Comparator must still return 0 when comparing an object with itself.

**Do not use** Objects.compare as a method to automatically check deep equality, replace Objects.equals, or auto-discover null policies/natural ordering. If there is no Comparator and the type implements Comparable, call compareTo directly when appropriate or use Comparator.naturalOrder() when a Comparator is needed.

## 12. Key takeaways

**Objects.compare(a, b, c)** has exactly two core execution branches:

1. a == b: returns 0 immediately.
2. a != b: returns the exact result of c.compare(a, b).

Negative/0/positive signs are always interpreted **according to the provided Comparator**. Two objects with different references, even if equals is true, still go through the Comparator. There is no built-in comprehensive null-handling mechanism beyond the same-reference case; when one argument is null, choose Comparator.nullsFirst or Comparator.nullsLast if business logic permits null. Do not infer that compare == 0 always implies Object.equals is true, especially when using custom Comparators with TreeSet/TreeMap.