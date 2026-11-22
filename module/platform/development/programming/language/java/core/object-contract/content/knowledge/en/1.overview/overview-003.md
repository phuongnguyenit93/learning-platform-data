# Distinguishing Object Identity, Value Equality, and Ordering in Java

When working with an object, three seemingly similar questions actually have different meanings:

1. **Identity:** Do two variables point to **the same object** in memory?
2. **Value equality:** Are two objects considered **equivalent according to the data type's or business rules**?
3. **Ordering:** Which object comes before, after, or ranks equal to another **according to a sorting criterion**?

In Java, these three concepts correspond respectively to `==`, `equals()`/`hashCode()`, and `Comparable`/`Comparator`. Choosing the wrong one can make `HashSet`, `HashMap`, `TreeSet`, and `TreeMap` behave differently from expectations.

## 1. Comparison Table

| Aspect | Question | Tool | Result |
|---|---|---|---|
| Identity | Is it the same object? | `a == b` for two references | `boolean` |
| Equality | Same value per the type's definition? | `a.equals(b)`, `Objects.equals(a,b)` | `boolean` |
| Value hashing | Do two equal values have the same hash code? | `hashCode()` paired with `equals()` | `int`, not an equality test |
| Natural ordering | Which object comes first by default? | `Comparable<T>.compareTo(T)` | Negative, `0`, positive |
| Custom ordering | Which object comes first by a chosen criterion? | `Comparator<T>.compare(a,b)` | Negative, `0`, positive |

**`a == b`, `a.equals(b)`, and `compare(a,b) == 0` are not inherently equivalent.** Two books can be two different instances with the same information; two different books can rank equal when a comparator only considers publication year.

## 2. Identity: Same Object or Different Object?

For **reference types**, `==` returns `true` when two variables point to the same instance (or both are `null`). This operation does not inspect attributes inside the object.

~~~java
String first = new String("java");
String second = new String("java");
String alias = first;

System.out.println(first == second);      // false
System.out.println(first == alias);       // true
System.out.println(first.equals(second)); // true
~~~

This is an **illustrative snippet** that can be placed inside `main`, not a standalone Java file. Two `new String` calls create two instances; `alias` points to the same instance as `first`. `String.equals` compares the character sequences, so the two instances are still equal in content.

For **primitive types** (`int`, `boolean`, `char`...), `==` compares primitive values. Do not use incidental outcomes of string interning or wrapper caching (`Integer`) to conclude that `==` compares object contents: those mechanisms may reuse instances in certain cases.

Identity is useful when an algorithm genuinely needs to know **whether it is the same object in memory**, such as checking aliases or traversing an object graph by identity. `IdentityHashMap` is a specialized structure that uses identity for keys; a regular `HashMap` uses value equality. `System.identityHashCode(x)` is helpful for diagnostics, but it is **not a unique ID** and does not prove two objects are the same, because hash collisions can still occur.

## 3. Value: `equals()` and `hashCode()`

`Object.equals()` defaults to meaning identity. Types such as `String`, `BigDecimal`, and many value objects redefine equality based on content. You must clearly decide **which attributes participate in defining equality**:

- **Value objects** such as coordinates or a monetary amount: usually equal when all meaningful components are equal; immutability helps when used as keys.
- **Entities** such as orders: usually need to be distinguished by a stable identifier; descriptive fields may change while the entity remains the same. Care must be taken with unassigned or mutable IDs.
- **`record`**: Java automatically generates `equals()`/`hashCode()` from its components. A record **does not automatically generate `Comparable`**. If a component is an array, comparing that component still uses the array's default equality (identity), rather than deeply comparing each element.

The `equals()` contract requires:

1. **Reflexive:** `x.equals(x)` is always true.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` yield the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` must be true.
4. **Consistent:** when the data used to check equality does not change, repeated calls return the same result.
5. **Non-null:** for non-`null` `x`, `x.equals(null)` returns `false`.

If `a` can be `null`, calling `a.equals(b)` risks a `NullPointerException`; use `Objects.equals(a,b)` for null-safe comparison. When implementing equality manually, `Objects.equals` can help with fields, while `Arrays.equals`/`Arrays.deepEquals` are useful if array contents need to be compared.

### Why Does `hashCode()` Go Together With `equals()`?

The mandatory rule is: **if `x.equals(y)`, then `x.hashCode() == y.hashCode()`.** The converse is not required: two different objects can still share the same hash. When overriding `equals()`, you must override `hashCode()` accordingly. Hash-based collections use the hash to select a lookup bucket and equality to distinguish specific keys.

If an object is already in a `HashSet` or used as a `HashMap` key, changing fields that participate in equality/hash can prevent lookups or removals from finding the element again. Prefer immutable keys. With inheritance, equality design must avoid breaking symmetry or transitivity.

## 4. Ordering: `Comparable` and `Comparator`

The result of an ordering comparison only requires checking the **sign**:

- **Negative:** the left operand comes before the right operand.
- **`0`:** the two operands rank equal **according to the sorting criterion**.
- **Positive:** the left operand comes after the right operand.

You must not assume the result is only `-1`, `0`, or `1`.

**`Comparable<T>`** is implemented inside a type via `compareTo` when the type has a sensible natural order. **`Comparator<T>`** is an external rule that can be chosen differently at each call site: by name, by age, by price... For example, a comparator sorting ascending by string length, then alphabetically when lengths are equal:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());

System.out.println(byLengthThenText.compare("an", "be") < 0);  // true
System.out.println(byLengthThenText.compare("a", "bbb") < 0); // true
~~~

This is an illustrative snippet placed inside `main` with `import java.util.Comparator;`. The `thenComparing` method acts as a **tie-breaker** when the first criterion is equal. `reversed()`, `nullsFirst`, `nullsLast`, `comparingInt`, and `comparingLong` can be used when appropriate. If values can be `null`, an explicit policy must be chosen rather than letting the comparator throw an unexpected exception.

The ordering contract requires that the sign of `compare(a,b)` be the opposite of `compare(b,a)`, the before/after relation be **transitive**, and when `compare(a,b) == 0`, comparing `a` and `b` against the same `z` must produce the same sign. Avoid `return a.score - b.score;` because subtraction can overflow `int`; use `Integer.compare(a.score, b.score)` or `Comparator.comparingInt(...)`.

## 5. A Java 17 Program Demonstrating All Three Concepts

In this example, `Book` is a record whose equality is based on both `isbn` and `title`. Its natural ordering also checks those exact two components, so **for Book**, `compareTo(...) == 0` is consistent with `equals()`. `Ticket` uses an external comparator to illustrate a comparator that can group two different objects into the same ordering equivalence group. Finally, `BigDecimal` shows an exception where a natural ordering is inconsistent with `equals()`.

Save the complete program as **`ObjectContractDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class ObjectContractDemo {
    record Book(String isbn, String title) implements Comparable<Book> {
        @Override
        public int compareTo(Book other) {
            return Comparator.comparing(Book::isbn)
                    .thenComparing(Book::title)
                    .compare(this, other);
        }
    }

    record Ticket(String id, int priority) {}

    public static void main(String[] args) {
        Book first = new Book("978-1", "Java");
        Book equalValue = new Book("978-1", "Java");
        Book other = new Book("978-2", "Concurrency");

        System.out.println("Book ==: " + (first == equalValue));
        System.out.println("Book equals: " + first.equals(equalValue));
        System.out.println("Book hash equals: "
                + (first.hashCode() == equalValue.hashCode()));
        System.out.println("Book compare = 0: "
                + (first.compareTo(equalValue) == 0));
        System.out.println("Book first < other: "
                + (first.compareTo(other) < 0));
        System.out.println("HashSet<Book>: "
                + new HashSet<>(List.of(first, equalValue, other)).size());
        System.out.println("TreeSet<Book>: "
                + new TreeSet<>(List.of(first, equalValue, other)).size());

        Ticket a = new Ticket("A", 1);
        Ticket b = new Ticket("B", 1);
        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);
        TreeSet<Ticket> byPrioritySet = new TreeSet<>(byPriority);
        byPrioritySet.add(a);
        byPrioritySet.add(b);
        System.out.println("Ticket equals: " + a.equals(b));
        System.out.println("Ticket compare = 0: "
                + (byPriority.compare(a, b) == 0));
        System.out.println("TreeSet priority only: " + byPrioritySet.size());

        Comparator<Ticket> byPriorityThenId =
                byPriority.thenComparing(Ticket::id);
        TreeSet<Ticket> distinctTickets = new TreeSet<>(byPriorityThenId);
        distinctTickets.add(a);
        distinctTickets.add(b);
        System.out.println("TreeSet priority + id: "
                + distinctTickets.size());

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("BigDecimal equals: " + x.equals(y));
        System.out.println("BigDecimal compare = 0: "
                + (x.compareTo(y) == 0));
        System.out.println("HashSet<BigDecimal>: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet<BigDecimal>: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ObjectContractDemo.java
java ObjectContractDemo
~~~

Output:

~~~text
Book ==: false
Book equals: true
Book hash equals: true
Book compare = 0: true
Book first < other: true
HashSet<Book>: 2
TreeSet<Book>: 2
Ticket equals: false
Ticket compare = 0: true
TreeSet priority only: 1
TreeSet priority + id: 2
BigDecimal equals: false
BigDecimal compare = 0: true
HashSet<BigDecimal>: 2
TreeSet<BigDecimal>: 1
~~~

**Result analysis:**

1. `first` and `equalValue` are two instances (`== false`) yet equal in value. The record generates matching `equals` and `hashCode`; `Book`'s `compareTo` also returns `0`.
2. `HashSet<Book>` relies on equality/hash; `TreeSet<Book>` relies on natural ordering. Both keep the exact two distinct books.
3. The two `Ticket` instances have different IDs so `equals` is `false`, but the comparator only inspects `priority` and returns `0`. `TreeSet` treats them as **one key** and keeps only one element. When adding `id` as a tie-breaker, both are retained.
4. `BigDecimal("2.0")` differs from `BigDecimal("2.00")` according to `equals`, because `equals` also considers **scale** (1 versus 2). However, `compareTo` compares numerical value and returns `0`. Therefore, the hash set keeps 2 while the tree set keeps 1. **`BigDecimal`'s natural ordering is famously inconsistent with `equals`.**

## 6. `compare == 0` Does Not Imply Same Value

A comparator defines **equivalence groups for sorting**. A comparator that only looks at exam scores may treat two students with different student IDs as tied. This is fine when sorting a list, but has a major impact if the comparator is used to define keys.

| Structure/operation | Equality or ordering rule |
|---|---|
| `HashSet`, `HashMap` | `equals()` combined with `hashCode()` |
| `TreeSet`, `TreeMap` | `compareTo()` or `Comparator.compare()`; `0` means the same key |
| `List.sort()`, `Collections.sort()`, `Stream.sorted()` | Sorts according to the comparator, **does not automatically remove tied elements** |
| `List.contains()` | Checks using `equals()` |

For objects used as keys in a sorted set/map, you **should** choose an ordering consistent with equality if feasible: `compare(a,b) == 0` if and only if `a.equals(b)`. If you intentionally use a comparator to group items by score or priority, clearly document that meaning and accept that the set/map will keep only one key per group.

Consistency must also account for objects that have **the same equality but different data used for sorting**. For example, if an entity's equality only checks ID, a comparator by `name` then ID is not necessarily consistent: two instances with the same ID but different names may yield a non-`0` result. When designing a key mechanism, you must decide whether the entity is immutable and on which fields.

Do not mutate fields involved in a comparator while an object is inside a `TreeSet`/`TreeMap`: the node's sorted position was built from the old value, making lookup, removal, or duplicate detection unreliable.

## 7. How to Choose in Practical Scenarios

| Requirement | Appropriate operation/design | Things to note |
|---|---|---|
| Check same instance | `a == b` | Identity only for references |
| Compare string or value object content | `Objects.equals(a,b)` | Safe when `null` is present |
| Create keys for hash map/set | `equals` + `hashCode` with same logic | Key fields should be immutable |
| Sort by default order | `Comparable` | Not every type has a natural ordering |
| Sort by multiple criteria chosen at runtime | `Comparator`, `thenComparing` | Tie-break if deterministic order is needed |
| Keep multiple elements with the same score in `List` | `List.sort(comparator)` | No tie-breaker needed to retain elements |
| Keep multiple elements in `TreeSet` | Comparator distinguishing by appropriate keys | `compare == 0` is treated as one element |
| Compare `BigDecimal` magnitude ignoring scale | `compareTo(...) == 0` | `equals` considers scale |
| Compare array contents | `Arrays.equals` or `Arrays.deepEquals` | `array.equals` defaults to identity |

Design workflow: **(1)** determine whether it is an entity or a value object; **(2)** define the fields participating in equality; **(3)** preserve the hash contract; **(4)** choose a natural ordering and/or comparator; **(5)** verify whether `compare == 0` fits the intended collections; **(6)** test symmetry, transitivity, and rule stability.

## 8. Common Mistakes to Avoid

1. **Using `==` to compare two `String` or wrapper objects:** yields results depending on instances or caching mechanisms instead of content.
2. **Overriding `equals` without overriding `hashCode`:** breaks the contract in hash sets/maps.
3. **Treating matching hashes as equal values:** hash collisions are valid, not proof of equality.
4. **Comparing only one non-unique field in a `TreeSet` comparator:** accidentally drops distinct elements.
5. **Comparing integers by subtraction:** overflow can invert the ordering.
6. **Non-transitive comparator or one depending on mutating data:** sorting results and trees can become unstable, violating the contract.
7. **Modifying equality/hash/order fields of a key already added to a set/map:** may fail to look up or remove it.
8. **Assuming a record always deep-compares arrays:** array-typed components still use default reference equality.
9. **Assuming `compareTo == 0` always implies `equals == true`:** the classic counterexample is `BigDecimal`.

## 9. Self-Check Questions

**1.** Two variables point to the same instance; the value of a mutable field changes. Does the result of `==` between the two variables change?  
**Answer:** No. They still point to the same object; equality with *another* object may change depending on the implementation.

**2.** Is `a.equals(b) == false` with equal `hashCode()` values valid?  
**Answer:** Yes, because hash collisions are allowed. The mandatory direction is that when equality is true, hashes must be equal.

**3.** Two orders have different IDs but the same creation date, and a comparator only compares dates and returns `0`. What happens when adding both to a `TreeSet`?  
**Answer:** The set keeps only one element according to the comparator; to distinguish by ID, an appropriate additional criterion is needed.

**4.** When sorting a list of employees by age while keeping everyone of the same age, is it mandatory to tie-break by ID?  
**Answer:** No. Sorting a `List` does not remove elements. Tie-breaking is needed when you want deterministic ordering among equal-age cases, or when using the comparator to define key identity in a sorted set/map.

**Takeaway:** **Identity** answers *same object?*; **equality** answers *same value per what rules?*; **ordering** answers *before/after/equal by what criteria?* Design and test each relationship separately.