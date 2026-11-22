# Keeping equals() Easy to Understand, Free of Side Effects, and Exception-Free for Normal Data

## 1. Goals When Implementing equals(Object)

`equals(Object)` answers one question: **is the object receiving the call considered equal to the object passed in?** When implementing this method, a good design needs to simultaneously meet three practical requirements:

1. **Easy to understand:** a reader looking at it can immediately tell which attributes the class uses to determine equality, which conditions return `true`, and which conditions return `false`.
2. **Free of side effects:** calling `equals` only observes the data used for comparison; it does not alter object state, does not modify the argument, does not write data elsewhere, and does not trigger business actions.
3. **Does not throw exceptions on normal data:** `null`, objects of different types, and data fields allowed to be `null` must be handled properly, instead of accidentally raising `NullPointerException` or `ClassCastException`.

These are design principles when **implementing** the `Object.equals(Object)` contract. In particular, for any non-`null` object `x`, `x.equals(null)` must return `false`. Calling `x.equals(y)` when `x == null` itself still causes `NullPointerException`: no instance method can execute on a `null` reference.

The requirement “does not throw exceptions” should not be interpreted as a promise that every JVM error, corrupted-state object, or extraordinary situation is swallowed. The goal here is **not turning valid, common comparison inputs into exceptions**; invalid data should be validated at object creation or update boundaries.

## 2. Why Does equals Need to Be Pure and Stable?

Library components such as `HashSet`, `HashMap`, and search algorithms may call `equals` multiple times, with order or frequency depending on how they operate. They rely on the equality contract consisting of reflexivity, symmetry, transitivity, consistency, and the `null` rule.

If `equals` increments a counter, updates an attribute, consumes an element from an iterator, makes a network call, writes to a database, or emits an event, **merely checking equality** has created an unexpected mutation. If the result depends on time, external service state, or comparison count, two objects can sometimes be equal and sometimes not even though the data serving as the equality key has not changed. That behavior is hard to test and can make collection lookups unreliable.

Distinction:

| Property | Preferred approach | Signs to avoid |
| --- | --- | --- |
| Comparison | Check identity, type, and equality-defining fields | Nesting complex business branches or fetching data from external services |
| State | Read only stable attributes | Incrementing `comparisonCount`, marking “checked”, updating the object |
| Valid missing values | Compare safely using `Objects.equals` | Calling methods on nullable fields without checking |
| Different type | Return `false` | Unconditional cast followed by `ClassCastException` |
| Stability | Same data, same result when no relevant changes occur | Depending on randomness, clocks, or network data |

A good `equals` method is usually short: check whether it is the same reference, check the type, then compare each equality-defining field. Whether to use `instanceof` or `getClass()` must match the equality policy of the class hierarchy; the example below uses a `final` class, so no differences arise across subclasses.

## 3. Runnable Java 17 Example: Immutable Value Object

Suppose a document key is identified by a mandatory `code` and an `edition` that is allowed to be `null`. Two keys are equal when **both** corresponding fields are equal. Because the document code must not have an absent reference, the constructor validates `code` at creation time; the comparison does not need to handle an internal state that is already forbidden.

Save the following program to **EqualsDesignDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsDesignDemo {
    static final class DocumentKey {
        private final String code;
        private final String edition; // Allowed to be null

        DocumentKey(String code, String edition) {
            this.code = Objects.requireNonNull(code, "code");
            this.edition = edition;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof DocumentKey that)) {
                return false; // Includes both null and objects of other types
            }
            return code.equals(that.code)
                    && Objects.equals(edition, that.edition);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, edition);
        }
    }

    public static void main(String[] args) {
        DocumentKey a = new DocumentKey("D-07", null);
        DocumentKey same = new DocumentKey("D-07", null);
        DocumentKey newer = new DocumentKey("D-07", "v2");

        System.out.println("self: " + a.equals(a));
        System.out.println("equal values: " + a.equals(same));
        System.out.println("symmetric: " + same.equals(a));
        System.out.println("different edition: " + a.equals(newer));
        System.out.println("null: " + a.equals(null));
        System.out.println("other type: " + a.equals("D-07"));
        System.out.println("same hash: " + (a.hashCode() == same.hashCode()));

        Set<DocumentKey> keys = new HashSet<>();
        keys.add(a);
        System.out.println("HashSet contains equal key: " + keys.contains(same));

        boolean first = a.equals(same);
        boolean second = a.equals(same);
        System.out.println("repeated result: " + (first == second));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac EqualsDesignDemo.java
java EqualsDesignDemo
~~~

Output:

~~~text
self: true
equal values: true
symmetric: true
different edition: false
null: false
other type: false
same hash: true
HashSet contains equal key: true
repeated result: true
~~~

**Why does this code meet the goals?**

- `this == other` returns `true` when comparing an object to itself, without needing to check individual fields.
- `other instanceof DocumentKey that` only succeeds when `other` is non-`null` and of the right type to compare. `null instanceof DocumentKey` is `false`; an argument of another type also gets `false` without a bad cast.
- `code` is validated non-`null` at creation and is `final`, so `code.equals(that.code)` is safe for every validly constructed `DocumentKey` object.
- `edition` can be `null`. `Objects.equals(edition, that.edition)` yields `true` when both are `null`, `false` when only one side is `null`, and uses `String.equals` when needed; **this is a comparison of two data fields**, not a comparison of the whole `DocumentKey` against `null`.
- There are no field assignments, file reads/writes, logging, network access, or parameter mutations in `equals`. Both attributes are immutable strings held in `final` fields, so repeated comparisons on the same unchanged objects give the same result.
- `hashCode()` uses the exact fields participating in `equals`. Equal objects have the same hash code, satisfying the necessary condition of the contract when placed into a `HashSet` or used as a `HashMap` key. The converse **is not required**: equal hash codes do not prove two objects are equal.

The line `repeated result: true` shows that two results in the example match. Such a check **is not enough by itself to prove** the method has no side effects: to ensure that, you must inspect the code and potentially verify object state before/after calls.

## 4. Common Implementation Mistakes

### 4.1. Casting before checking

~~~java
@Override
public boolean equals(Object other) {
    DocumentKey that = (DocumentKey) other;
    return code.equals(that.code);
}
~~~

This is an **illustrative erroneous snippet inside class DocumentKey**, not a standalone program. If `other == null`, the cast yields `null`, yet `that.code` causes `NullPointerException`. If `other` belongs to an incompatible type, the cast can cause `ClassCastException`.

Fix with `instanceof` or checking `null` and type before accessing fields. This also helps readers clearly see the equality rejection cases.

### 4.2. Calling equals on a nullable field

~~~java
return code.equals(that.code)
        && edition.equals(that.edition); // May throw NullPointerException
~~~

This is an **illustrative erroneous expression inside equals**. `edition` is allowed to be `null`, so `edition.equals(...)` is unsafe. Write `Objects.equals(edition, that.edition)` to clearly express that either side can be absent.

There is no need to use `Objects.equals` for every field out of habit: if the class invariant guarantees a field is non-`null`, calling `code.equals(...)` remains easy to read and safe.

### 4.3. Turning comparison into an update operation

~~~java
private int comparisonCount;

@Override
public boolean equals(Object other) {
    comparisonCount++; // Side effect: merely reading equality mutates state
    // ... perform comparison
}
~~~

This is an **illustrative antipattern snippet**, not a standalone runnable program. Even if the counter does not alter the result, the method still creates a side effect and can cause problems when multiple threads compare concurrently. Logging, mutating the input object, sanitizing data fields right inside `equals`, persisting data, or emitting events also should not be in the comparison path.

If `code` needs normalization for case-insensitive comparison or whitespace trimming, define a clear rule and **normalize when constructing the value**, or use an appropriate pure comparison; do not silently mutate fields inside `equals`. The normalization rule must be consistent with `hashCode`.

### 4.4. Using external services as comparison criteria

For example, `equals` calls an API to fetch a current name, or queries a database to see whether two codes still map to the same record. At that point the answer depends on service state, network errors, and call timing; the result can change when neither object's fields have changed.

Separate lookup or state-update operations from `equals`. If equality genuinely needs a value from another system, decide beforehand how that value will be captured and stored in the object. For immutable objects, use only data fields already determined at creation time.

### 4.5. Swallowing all errors with catch

~~~java
@Override
public boolean equals(Object other) {
    try {
        DocumentKey that = (DocumentKey) other;
        return code.equals(that.code);
    } catch (Exception ignored) {
        return false;
    }
}
~~~

This is an **illustrative erroneous snippet**, not a standalone program. `catch (Exception)` hides implementation bugs and conflates programming errors with “not equal”. It also makes detecting corrupted state harder.

Fix the root cause directly: check the type, handle nullable fields safely, and validate invariants at object creation. Return `false` for the normal cases of different type or `null`; do not use exceptions as control flow for them.

### 4.6. Calling Objects.equals(this, other) directly inside equals

~~~java
@Override
public boolean equals(Object other) {
    return Objects.equals(this, other);
}
~~~

This snippet is also **invalid as an equals implementation**. When `this` and `other` do not share the same reference and are both non-`null`, `Objects.equals(this, other)` will call `this.equals(other)` again, causing unbounded recursion and eventually potentially leading to `StackOverflowError`. `Objects.equals` is appropriate for comparing **data fields** inside `equals` or two nullable objects outside the method.

## 5. Keeping Logic Readable While Staying Contract-Compliant

A generally sensible implementation order is:

1. Confirm `this == other`.
2. Reject `null` and wrong-type cases with a clear type check.
3. Compare the fields that genuinely determine equality, with `null` handling matching each field's invariant.
4. Override `hashCode` from the same field set and maintain stability while the object is used as a key.

Avoid expanding the comparison to presentation-only fields, temporary data, access counters, or information that can change independently of business identity, unless the equality model **truly** requires them. If a class needs to mutate fields participating in `equals`/`hashCode`, evaluate the impact on `HashSet`/`HashMap`: changing the hash code while the object is an element/key can cause lookups to fail. Whenever possible, prefer immutable value objects.

Also avoid trying to “optimize” by writing to a mutable cache inside `equals`. Even a cache that does not alter the logical result can bring along side effects, synchronization issues, or unnecessary complexity. If optimization is needed due to real measured metrics, design a dedicated solution and verify the entire contract.

## 6. Checks Upon Completion

For a custom `equals` method, ask yourself:

- Is `x.equals(x)` `true` for every valid object `x`?
- Does `x.equals(null)` return `false`, and does `x.equals(objKhacKieu)` return `false` without throwing `ClassCastException`?
- Are valid nullable fields compared without throwing `NullPointerException`?
- Do two equal objects yield the same `hashCode`? Is the result symmetric, transitive, and consistent when relevant fields do not change?
- Are there any assignments, resource reads/writes, network queries, logging, or input object mutations inside `equals`?
- Are the equality-defining attributes stable while the object is used as a key or element in hash-based structures?

These questions can be turned into JUnit tests: call `equals` multiple times, compare in both directions, put an element into a `HashSet` and look it up with an equal object, test `null`/wrong type/nullable fields, and ensure observable state does not change. Tests add protection for the contract; source code inspection remains necessary to confirm there are no hidden side effects.

**Key takeaway:** `equals(Object)` should be a clear, stable equality check that does not update state and returns normal results for `null`, different types, and valid nullable values. Immutable design and using the exact same fields in `hashCode` keep that behavior solid when objects participate in collections.