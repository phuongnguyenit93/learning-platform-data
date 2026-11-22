# Unequal Objects Are Still Allowed to Share a Hash Code

In Java, `hashCode()` returns an `int` integer used to support hash-based lookup structures, such as `HashMap` and `HashSet`. **A hash code is not a unique identifier of an object.** Two objects that are **unequal according to `equals`** can still receive the **same hash code**. This phenomenon is called a **hash collision**.

The mandatory part of the `hashCode` contract is the opposite direction: if `x.equals(y)` returns `true`, then `x.hashCode()` **must equal** `y.hashCode()`. Distinguishing these two directions of reasoning accurately is essential for implementing `equals`, `hashCode`, and using Java collections properly.

## 1. The `hashCode` Contract: What Does It Require and What Does It Not?

For two non-`null` objects `x` and `y`, the essential condition is:

~~~text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
~~~

That is a **one-way implication**. The following table distinguishes the cases:

| `x.equals(y)` | `x.hashCode() == y.hashCode()` | Is It Valid? | Meaning |
| --- | --- | --- | --- |
| `true` | `true` | **Mandatory** | Objects equal by `equals` must share the same hash code. |
| `true` | `false` | **Contract violation** | Two equal values have different hash codes. |
| `false` | `true` | **Valid** | Two unequal values share the same hash code: a collision. |
| `false` | `false` | **Valid** | Two unequal values have different hash codes. |

You must not infer:

~~~text
x.hashCode() == y.hashCode()  =>  x.equals(y)
~~~

This inference is **wrong**. Equal hashes only state that two objects produced the same output from the hash function; they do **not** confirm that the objects are equal in business meaning or share the same identity.

In addition, the `hashCode` contract requires that multiple calls to `hashCode()` on the same object during a single Java execution return the same result **provided no information used in `equals` comparisons has changed**. Java does not require an object to always have the same hash code across different JVM runs; some types like `String` have a specified hash algorithm, but you should not generalize that guarantee to every class.

### Why Are Hash Collisions Inevitable in General?

`hashCode()` returns a 32-bit `int`, meaning there are only **2³² distinct bit values**. Meanwhile, the number of possible values or object states can be vastly larger. When mapping more input values than possible outputs into a 32-bit integer, by the pigeonhole principle, at least two input values must share the same hash code.

Therefore, **a good hash function aims to distribute values effectively and remain consistent with `equals`**, rather than promising that every pair of unequal objects receives a distinct hash.

## 2. A Deterministic Example: `"Aa"` and `"BB"`

Java's `String.hashCode()` uses an accumulation formula with multiplier 31 over UTF-16 `char` values. For two two-character strings:

~~~text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
~~~

Despite having the same hash code `2112`, `"Aa".equals("BB")` is still `false` because the string contents differ.

File **`StringCollisionDemo.java`** (Java 17+):

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringCollisionDemo {
    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";

        System.out.println(first.equals(second));
        System.out.println(first.hashCode());
        System.out.println(second.hashCode());
        System.out.println(first.hashCode() == second.hashCode());

        Set<String> unique = new HashSet<>();
        unique.add(first);
        unique.add(second);
        unique.add(new String("Aa"));
        System.out.println(unique.size());
        System.out.println(unique.contains(new String("BB")));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(first, 10);
        scores.put(second, 20);
        System.out.println(scores.size());
        System.out.println(scores.get("Aa"));
        System.out.println(scores.get("BB"));

        scores.put(new String("Aa"), 99);
        System.out.println(scores.size());
        System.out.println(scores.get("Aa"));
    }
}
~~~

Compile and run:

~~~bash
javac StringCollisionDemo.java
java StringCollisionDemo
~~~

Exact output:

~~~text
false
2112
2112
true
2
true
2
10
20
2
99
~~~

Analysis:

1. `first.equals(second)` is `false`: the two strings have different contents.
2. Both `hashCode()` calls return `2112`: a **collision** has occurred.
3. `HashSet` accepts both `"Aa"` and `"BB"` because they are **not equal according to `equals`**; the element count after two additions is two. Adding `new String("Aa")` does not introduce a newly distinct value under `String.equals`, so the size remains `2`.
4. `HashSet.contains(new String("BB"))` is `true`: despite a different reference, the query object equals `"BB"` under `equals`.
5. `HashMap` maintains two separate mappings `"Aa" → 10` and `"BB" → 20`. They share a hash but are **different keys** under `equals`; one entry does not overwrite the other.
6. Putting a value again with `new String("Aa")` replaces the value for the key equal to `"Aa"`, so the map size stays `2` and `get("Aa")` returns `99`.

The example intentionally prints sizes, containment checks, and lookups by key. **Do not print the whole `HashSet`/`HashMap` to infer ordering**, because the iteration order of these structures is not guaranteed by the API contract.

## 3. How Do `HashSet` and `HashMap` Handle Collisions?

A practical view of hash-based lookup:

1. The collection gets `hashCode()` from the key or element.
2. It uses the hash information to determine a candidate slot/group in its internal structure.
3. If multiple candidates land in the same slot, it still has to distinguish **which keys are equal according to `equals`**.
4. If two keys are equal, `HashMap.put` updates the existing mapping and `HashSet.add` does not add a new element. If two keys are unequal, both can coexist simultaneously despite having the same hash code.

Conceptual diagram (this is an explanatory model, not an exact step-by-step description of every JVM version's implementation):

~~~text
                       hashCode()
                     /            \
                value A          value B
                     \            /
                   Same hash group
                    /           \
                equals?       equals?
                /    \         /    \
              true  false    true   false
              same  diff     same   diff
              key   key      key    key
~~~

A **hash code collision** means two objects have the same `hashCode()` value. A **bucket collision** means they are mapped into the same internal storage slot. Because a hash table has a finite number of buckets, two **different** hash codes can still land in the same bucket. Do not conflate the two cases; Java may mix bits and change how buckets are organized depending on the version and conditions.

Modern `HashMap` implementations have mechanisms to manage collision groups, and in certain situations can convert a bucket's list structure into a tree. That is an **implementation detail**, not a guarantee that every collision is always handled in a fixed number of comparisons. Hash distribution quality still affects performance.

### Two Key Points for Collections

- **Correctness:** having the same hash code is **not enough to conclude duplicate keys**. The collection also needs to apply the key's equality rules.
- **Performance:** many distinct keys piling into the same group can increase the number of checks or lookup cost. Well-distributed hash codes generally help `HashMap`/`HashSet` operate efficiently.

Thus, an isolated collision is **not a bug**. Bugs arise when `equals`/`hashCode` violates the contract, or when a developer uses the hash as the sole equality check.

## 4. Custom Class Example: Intentionally Identical Hashes While `equals` Remains Correct

To see that valid collisions do not depend on `String`, let us create a `TicketKey` value object. Two tickets are equal when they have the same `code`. The following example intentionally returns the same hash code `1` for **every** `TicketKey`.

File **`ConstantHashDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ConstantHashDemo {
    static final class TicketKey {
        private final String code;

        TicketKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof TicketKey that)) {
                return false;
            }
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            // Only to illustrate collision: very poor distribution.
            return 1;
        }
    }

    public static void main(String[] args) {
        TicketKey a = new TicketKey("A");
        TicketKey sameValue = new TicketKey("A");
        TicketKey b = new TicketKey("B");

        System.out.println(a == sameValue);
        System.out.println(a.equals(sameValue));
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<TicketKey> tickets = new HashSet<>();
        tickets.add(a);
        tickets.add(sameValue);
        tickets.add(b);

        System.out.println(tickets.size());
        System.out.println(tickets.contains(new TicketKey("B")));
    }
}
~~~

Compile and run:

~~~bash
javac ConstantHashDemo.java
java ConstantHashDemo
~~~

Exact output:

~~~text
false
true
false
true
2
true
~~~

`a` and `sameValue` are two instances that are equal according to `equals` and have the same hash code `1`: **contract-compliant**. `a` and `b` are unequal yet have the same hash code `1`: **also contract-compliant**. `HashSet` still distinguishes the two values `"A"` and `"B"`; hash codes do not need to differ in order to store two elements.

However, **you should not use a constant hash in real applications**, because dumping every key into the same hash group degrades lookup efficiency when there are many elements. A more suitable implementation for `TicketKey`'s definition is:

~~~java
@Override
public int hashCode() {
    return code.hashCode();
}
~~~

Because the constructor rejects `null` and `code` is an immutable `String`, this approach is easy to understand, stable, and matches `equals` using `code.equals(that.code)`. Yet **even a better hash function does not guarantee zero collisions**: `"Aa"` and `"BB"` are still proof of that.

## 5. Distinguishing Hash Code, Value Equality, and Identity

| Concept | How It Is Checked/Expressed | Is Uniqueness Guaranteed? |
| --- | --- | --- |
| Same instance | `x == y` on two references | Determines whether two variables point to the exact same object at the time of comparison. |
| Equal by the type's definition | `x.equals(y)`, or `Objects.equals(x, y)` when `null` handling is needed | Depends on the type's `equals` implementation. |
| Same hash code | `x.hashCode() == y.hashCode()` | **No.** Two unequal objects can still share a hash. |
| Identity hash code | `System.identityHashCode(x)` | **No.** Not a unique identifier and not a guaranteed memory address. |

`Object.equals` compares by identity by default. A class that does not override `equals` may treat two instances containing the same fields as unequal; that is the default semantics, not automatically a bug. When you want value equality, define `equals` appropriately for the type and maintain a matching `hashCode`. Even with a proper `equals`, never treat the result of `hashCode` as a stable ID for identifying objects across runs.

Functions like `Objects.hash(...)`, `Arrays.hashCode(...)`, or `String.hashCode()` all still return an `int`; they **do not eliminate the possibility of collisions**. They support consistency, maintainability, and appropriate hash distribution for the data, not as a replacement for `equals`.

## 6. Common Mistakes

### Mistake 1: Treating Two Identical Hashes as Two Identical Values

~~~java
// WRONG: collision causes two distinct strings to be treated as equal.
boolean same = first.hashCode() == second.hashCode();

// RIGHT for String: compare contents using equals.
boolean sameValue = first.equals(second);
~~~

If two values are truly equal, their hashes must match; but from matching hashes **you cannot infer backward** that two values are equal. In particular, never compare only hashes when writing `equals`, deduplicating data, or identifying unique cache entries.

### Mistake 2: Thinking `HashSet` Automatically Merges Every Key with the Same Hash

`HashSet` eliminates duplicate elements **according to `equals`**, not matching hashes. In the first example, both `"Aa"` and `"BB"` are retained. If two objects are actually equal yet have different hash codes due to a buggy implementation, the set may behave unexpectedly.

### Mistake 3: Overriding `equals` but Forgetting `hashCode`

~~~java
// Implements equals by code but keeps hashCode inherited from Object:
// two instances with the same code may have different hashes.
@Override
public boolean equals(Object other) {
    return this == other ||
           (other instanceof TicketKey that && code.equals(that.code));
}
~~~

The snippet above only illustrates the **bug of omitting a `hashCode` override**, not a complete class definition. If a developer implements `equals` based on `code` like this, they **must** implement a corresponding `hashCode`. Doing only half the job can cause `HashMap.get` to miss an equal key or `HashSet` to accept duplicate values.

### Mistake 4: Using a Mutable Object as a Key and Mutating Comparison Data

If a field participating in `equals` and `hashCode` changes after the object has been placed into a `HashMap`/`HashSet`, its storage slot may no longer correspond to the new hash code. In that case `contains`, `get`, or `remove` may fail to work as intended. For key/value objects, prefer immutable fields and defensively copy mutable arrays or collections if they participate in comparison.

### Mistake 5: Assuming “Bigger Hashes” or “No Collisions in Test Data” Is Enough

Hash values belong to the `int` range and may be negative, zero, or positive; absolute magnitude says nothing about quality. A small test suite encountering no collisions also **does not prove** that the hash function avoids collisions. What should be evaluated is consistency with `equals`, distribution across realistic data, and appropriate performance.

## 7. Designing `hashCode` Correctly and Usefully

When writing `equals`/`hashCode` for a value-representing class, you can follow this sequence:

1. Identify **the fields that determine equality**; if they differ by business logic, `equals` must return `false`.
2. Use that same information to compute `hashCode`. You can use `Objects.hash(a, b)` for normal fields, or `Arrays.hashCode(array)` / `Arrays.deepHashCode(array)` for arrays depending on how `equals` compares arrays.
3. Ensure **two objects considered equal by `equals` always have the same hash**, even if they are two different instances.
4. Accept that **two unequal objects can share a hash**; a reasonable goal is good distribution, not proving unique hashes.
5. Keep data affecting the hash stable while the object serves as a key in a hash collection.
6. Test with `HashSet`/`HashMap` across three cases: two equal instances, two unequal instances with colliding hashes, and two unequal instances with different hashes. Specifically verify insertion, lookup, and key updates.

For example, a `Point(int x, int y)` class using both `x` and `y` to determine equality can be written as:

~~~java
record Point(int x, int y) {}
~~~

A Java record generates consistent `equals` and `hashCode` based on its components; however, it **does not guarantee a unique hash code for every coordinate pair**. Additionally, if a record contains an array component, the generated equality for that array component does not automatically become deep content comparison; a custom design is needed if value semantics require that.

## 8. Self-Check Questions

1. `"Aa".equals("BB")` is `false` yet both strings have `hashCode() == 2112`. Does this violate Java's contract? Explain using the one-way implication.
2. If you put both `"Aa"` and `"BB"` into a `HashSet<String>`, how many elements will the set contain? Why?
3. If two unequal keys with the same hash code are used in a `HashMap`, does calling `put` with the second key necessarily overwrite the value of the first key?
4. A class has `equals` based on `id`, while `hashCode` returns the constant `7` for every instance. Is the contract violated? What is the main problem with this approach?
5. A class has `equals` based on `id` but inherits `Object.hashCode`. Why can two instances with the same `id` cause bugs when used as keys in a `HashMap`?
6. Why can checking for equal `hashCode` not replace `equals` comparison when checking whether two objects have the same value?

**Takeaway:** **Equal ⇒ same hash code** is a mandatory rule. **Same hash code ⇏ equal** because collisions are allowed and usually cannot be eliminated completely. `HashMap` and `HashSet` still distinguish keys by `equals`; the job of `hashCode` is to support efficient lookup, not to grant a unique identity to each object.
