# Distinguishing Value Equality from Reference Equality

Two variables can point to the same object. Two distinct objects can also represent the same value or the same business identifier. These are two different relations, and Java provides different mechanisms to express them.

In collections, confusing these two relations can lead to puzzling questions: why does `contains` find an object that was never added, why does a `HashSet` keep only one element, or why do two lists that print identically produce different comparison results?

This article uses Java 17 and focuses on distinguishing object identity from logical equality, then applies those concepts to elements, keys, and collections themselves. The complete program along with its run commands and output is in the experimental section. Other short Java snippets illustrate specific points in context.

## 1. Two Questions That Must Be Kept Separate

Suppose there are two product objects with the same code `P1`.

First question:

> Are these two variables pointing to the exact same object created in the program?

This is reference equality. For two reference operands of compatible types for comparison, we use `==`.

Second question:

> According to the rules of the class or the data model, are these two objects considered equal?

This is logical equality, typically expressed using `equals`.

These two questions can yield different results without any bug. You need to determine what you want to ask before choosing an operator or method.

| Scenario | Same reference? | Can be equal by value? |
| --- | --- | --- |
| Assigning `b = a` without reassigning either variable | Yes | Yes, given a valid `equals` contract on non-null objects |
| Creating two distinct string objects with the same content | No | Yes |
| Creating two distinct product objects with the same code used by the class as its equality criterion | No | Yes |
| Creating two objects that do not share the equality criterion | No | No |

"Equal by value" does not automatically mean that every internal field is identical. It must be understood according to the class contract; a class may choose a specific subset of attributes to define equality.

## 2. References and Variable Assignment

Consider the following snippet:

```java
Product first = new Product("P1", "Pen");
Product alias = first;
```

Diagram:

```text
first ----+
          |
          v
        one Product P1 object
          ^
          |
alias ----+
```

Assignment does not copy the object. It copies the reference value, causing both variables to point to the same object.

Therefore, `first == alias` is `true`.

If we continue:

```java
alias = new Product("P1", "Pen");
```

then `alias` switches to a different object. `first` still points to the original object. If the class considers two products with the same code to be equal, at this point:

- `first == alias` is `false`.
- `first.equals(alias)` can be `true`.

Do not use the phrase "same memory address" as a guarantee about a physical address observable by a Java program. What the operator checks is reference identity under the language model; the physical location of the object is a memory management detail.

## 3. == Means Different Things Depending on Operand Types

### 3.1. With Two References

Reference comparison returns `true` when:

- Both references point to the same object.
- Or both are `null`.

A null reference and a non-null reference are never equal under this operation.

Whether the comparison can even be written also depends on the static types of the two operands. Not every pair of unrelated classes can be compared with `==` in an arbitrary expression.

### 3.2. With Primitive Types

`==` on compatible primitive values checks value equality according to the rules for the operands, including numeric conversions when applicable.

Do not take the statement "`==` compares references" as a universal definition for all cases in Java. That statement only applies when the operation is a reference comparison.

### 3.3. Wrappers Can Make Expressions Subtle

If both operands are `Integer`, `==` performs reference comparison. If one side is `int`, the numeric expression requires unboxing to compare primitive values.

Therefore, when encountering a numeric comparison involving a wrapper, examine the types on both sides. Unboxing `null` will also throw a `NullPointerException`.

Detailed rules are specified in [JLS 17, Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).

## 4. equals Does Not Automatically Know Business Equality

### 4.1. Default Behavior of Object

If a class does not override `equals`, it inherits the default behavior from `Object`: for non-null references, two objects are considered equal by this method only when they are the exact same object.

For example, take two objects of a class containing only a `code` field:

```java
PlainProduct a = new PlainProduct("P1");
PlainProduct b = new PlainProduct("P1");
```

If the class does not override `equals`, `a.equals(b)` is `false`. Having fields that print the same does not make Java automatically generate an equality rule.

### 4.2. Overriding Expresses a Model Choice

One class might consider products with the same code to be equal. Another value type might require the code, unit, and version to all match.

There is no universal rule that every class must compare all of its fields. You need to determine:

1. What does the object represent?
2. Which attributes decide whether two representations are interchangeable for the purpose under consideration?
3. Are those attributes stable throughout the object's usage lifecycle?
4. Is the rule consistent with collections and hashing?

### 4.3. The Method Name Alone Is Not Enough: The Signature Must Be Exact

The proper overriding signature is:

```java
@Override
public boolean equals(Object other) {
    return other instanceof Product that && code.equals(that.code);
}
```

This is a method snippet placed inside a `Product` class that has a mandatory non-null `code` field and does not allow subclassing. The full program below presents the complete class, `hashCode`, and usage.

Writing `boolean equals(Product other)` creates an overload rather than overriding `Object.equals(Object)`. When a framework invokes the method using the signature that takes `Object`, it will not call the method the author thought they replaced.

Using `@Override` helps the compiler detect signatures that do not actually override as intended.

### 4.4. The Core Contract Must Be Upheld

A valid `equals` implementation must satisfy these properties on non-null objects:

- Reflexive: an object is equal to itself.
- Symmetric: swapping the comparison order does not change the conclusion.
- Transitive: if `a` equals `b` and `b` equals `c`, then `a` equals `c`.
- Consistent: repeated calls return the same result as long as the relevant data does not change.
- Comparing against `null` returns `false`.

These properties along with the related `hashCode` requirements are described in [Object.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

## 5. String: The Clearest Example of Two Objects with the Same Value

Consider this snippet:

```java
String first = new String("java");
String second = new String("java");
```

The two `new` expressions create two distinct string objects, so:

```text
first == second       -> false
first.equals(second)  -> true
```

`String.equals` compares string content according to the class contract. It does not require the two variables to reference the same object.

### 5.1. Literals and Interning Can Mask Bugs

Two string literals with the same content may share the same interned object according to language rules. This can cause an `==` check to accidentally yield the value comparison result the author wanted.

However, strings obtained from user input, files, builders, or other sources do not necessarily share the same reference as a literal. Therefore, using `==` to check string content is misguided, even if a few small cases evaluate to `true`.

There is no need to call `new String(...)` in production code just to avoid sharing. This article uses it to construct a clear experiment separating the two relations.

### 5.2. Equal According to Which Method?

`"Java"` and `"java"` are not equal according to `String.equals`.

If a workflow requires case-insensitive matching or custom normalization rules, you must choose an appropriate comparison operation. Do not assume that visual similarity or linguistic equivalence is automatically guaranteed by `String.equals`.

See the contract in [String.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#equals(java.lang.Object)).

## 6. Handling null When Comparing Values

### 6.1. Calling a Method on null Is an Error

The snippet:

```java
Product a = null;
a.equals(other);
```

throws a `NullPointerException` before `Product`'s equality logic can even be reached.

Conversely, a non-null object with a valid `equals` method must return `false` when passed `null`.

### 6.2. Objects.equals Expresses Null-Tolerant Comparison

You can use:

```java
boolean equal = Objects.equals(a, b);
```

Standard behavior of this method:

| a | b | Result |
| --- | --- | --- |
| `null` | `null` | `true` |
| `null` | Non-null | `false` |
| Non-null | `null` | `false` with a valid `equals` implementation |
| Non-null | Non-null | Delegates to the object's contractual equality |

`Objects.equals` does not reflectively inspect all fields to invent a new equality definition. Nor does it fix a class whose `equals` violates symmetry or transitivity.

See [Objects.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

### 6.3. Technically Null-Safe Is Not Always Business-Valid

Two `null` values are considered equal by `Objects.equals`. However, if a product code is mandatory, two products both missing a code should not be silently treated as valid just because of this expression.

Constructor design or data validation steps must enforce business invariants. In the complete program below, a product code is not allowed to be null.

## 7. Why Can a Collection Find an Object with a Different Reference?

Suppose `Product` considers two products with the same code to be equal:

```java
Product stored = new Product("P1", "Pen");
Product query = new Product("P1", "Blue pen");

List<Product> products = new ArrayList<>();
products.add(stored);
```

Even though `stored != query`, the call:

```java
products.contains(query);
```

can return `true` because the list searches for an element equal by value according to the contract, rather than searching strictly for the `query` reference.

Similarly, `products.remove(query)` can remove the stored element even though the passed-in object was never added.

### 7.1. The Purpose of the Equality Criterion

If the business requirement is to look up products by code, this may be the desired behavior.

If you need to remove a specific object instance within an object graph, code-based equality may not be appropriate. In that case, you must express the identity requirement explicitly rather than arbitrarily changing the class-wide `equals` just to serve one special operation.

### 7.2. Duplicate Elements in a List

A list can still contain two elements that are equal according to `equals`. `List` allows duplicates; equality does not automatically deduplicate elements when adding them to a list.

A call to `remove(Object)` on a standard list removes only one matching element according to the contract, not every equal object. Do not confuse an equality rule with a multiplicity policy.

## 8. HashSet and HashMap: equals Must Be Paired with hashCode

### 8.1. Two Equal Objects Represent One Set Element

A `HashSet<Product>` will retain only one element when two objects with different references are added if they are equal according to `equals` and have consistent `hashCode` values.

It represents a set of distinct values according to the element's equality rule, not a set of every `new` invocation.

### 8.2. Two Equal Keys Map to the Same Entry

With a `HashMap<Product, Integer>`:

```java
map.put(first, 10);
map.put(second, 20);
```

if the two keys are equal according to the contract and hash consistently, the map manages a single mapping for that key; the second `put` replaces the corresponding value.

Do not assume that the map's size equals the number of key objects created or the number of `put` calls made.

### 8.3. A Hash Code Is Not a Unique Identifier

The contract requires:

```text
a.equals(b) is true
    => a.hashCode() == b.hashCode()
```

The converse does not hold. Two unequal objects can still have the same hash code.

Nor should `System.identityHashCode` be used as a guaranteed globally unique identifier for every object. Identity hash codes can still collide; they do not replace reference comparison.

### 8.4. Do Not Use toString to Prove Identity

Two objects can have the same string representation without being equal, or be equal based on a selected subset of fields while having different string representations.

The default format like `ClassName@...` is also not a guaranteed memory address. Do not treat display output as the contract for `equals` or `==`.

## 9. Choosing an Equality Criterion for a Custom Class

### 9.1. Equality Must Reflect Object Meaning

In the `Product` example, the `code` determines equality, while the `label` does not participate. Two objects with the same code but different labels are still equal under that choice.

This fits a model that treats the code as the stable identifier of a product. If the model instead represents a full snapshot where label differences matter, a different rule must be chosen.

Do not copy a formula from an example into every class without first defining the semantics of the data.

### 9.2. Data Participating in Equality Should Be Stable

If an object is stored as an element in a hash set or used as a map key, mutating a field that participates in `equals` or `hashCode` can cause lookups to stop working as assumed.

You can mutate a display label without breaking equality if the label does not participate in the criterion. However, that policy must be designed from the start.

An approach that is generally easy to manage is using stable key values or immutable value types for the attributes involved in hashing.

### 9.3. Inheritance Requires Care

Subclasses that add state can make preserving symmetry and transitivity in `equals` difficult if the superclass and subclass apply different criteria.

The demonstration program uses a `final` class to bound the comparison scope and avoid introducing inheritance complications into the main example. This is a choice for the example, not a rule that every Java class must be `final`.

### 9.4. Records Provide a Default Rule, Not Every Business Decision

A record generates equality behavior based on matching the exact record class and comparing all components according to the record contract. That is convenient for many value data types.

However:

- Every component chosen as record state participates in the default rule.
- Reference components still rely on the respective equality of their types.
- Array components are not automatically deep-compared by content just because they are inside a record.

You still need to design components that fit your domain semantics. See [Record Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

## 10. Two Collections Can Be Distinct Objects Yet Equal

Now we are not just comparing elements; a list or set itself is also an object with an `equals` method.

### 10.1. List: Same Order and Pairwise Equal Elements

Two lists can belong to different implementation classes:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = new LinkedList<>(List.of("A", "B"));
```

`a == b` is `false`, whereas `a.equals(b)` is `true`.

The list contract checks both size and corresponding element pairs in exact order. Therefore:

```text
[A, B] differs from [B, A]
[A, A, B] differs from [A, B]
```

Do not replace `equals` with `containsAll` when the goal is list equality, because `containsAll` does not check order or element multiplicity.

See [List.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).

### 10.2. Set: Same Elements According to the Set Contract

A `HashSet` containing `A, B` and a `LinkedHashSet` containing `B, A` are equal according to the `Set` contract, even though their iteration orders differ.

A set does not consider iteration order to be part of general set equality. The elements themselves must still have a valid and consistent equality relation.

See [Set.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).

### 10.3. Map: Same Key-Value Mappings

Two standard maps are equal if they represent the same key-value mappings according to the `Map` contract, even if their implementation classes or iteration orders differ.

Comparing maps is not just comparing the key sets or just comparing the value collections. Which key maps to which value is the actual data being evaluated.

See [Map.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

### 10.4. Do Not Assume Every Collection Implements Element-Wise equals

`Collection` does not mandate a single shared content-equality formula across all data structures.

A concrete example is `ArrayDeque`: two distinct deques containing the same elements in the same order are still not considered equal by content by the class's `equals` method.

If you need to compare a queue by element sequence, you must choose an appropriate comparison procedure or representation rather than blindly calling `equals` and assuming list rules apply.

The [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) documentation notes that queue implementations generally do not define element-based `equals` and `hashCode` methods.

## 11. Arrays Require Dedicated Content Comparison Methods

### 11.1. Array equals Does Not Traverse Elements

Consider this snippet:

```java
int[] a = {1, 2};
int[] b = {1, 2};
```

Because these are two distinct array objects:

- `a == b` is `false`.
- `a.equals(b)` is also `false`.

To compare one-dimensional array contents, use `Arrays.equals(a, b)`, which returns `true`.

### 11.2. Nested Arrays and deepEquals

With:

```java
Object[] a = {new int[]{1, 2}};
Object[] b = {new int[]{1, 2}};
```

`Arrays.equals(a, b)` checks the outer elements using their standard equality. Those two elements are two `int[]` arrays with different references, so the result is `false`.

`Arrays.deepEquals(a, b)` handles nested array contents according to its contract and returns `true` in this example.

Do not interpret "deep" as automatically using reflection to compare all fields of arbitrary custom classes. For ordinary object elements, the object's own `equals` method still governs.

See [Arrays Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).

### 11.3. A List Containing Arrays Still Relies on the Array Element's Equality

If two lists contain distinct arrays that have the same content, the list contract does not automatically turn array element comparison into a deep content comparison.

This illustrates a general principle: collection equality builds on element equality; it does not override an element equality rule that fails to meet your requirements.

## 12. When Is Reference Identity Truly Needed?

Not every use of `==` on objects is wrong.

### 12.1. Tracking a Specific Object Instance

Scenarios that genuinely require identity include:

- Detecting whether two variables are aliases for the exact same object.
- Tracking visited nodes in an object graph when distinct nodes might be equal by value.
- Preserving object-sharing relationships when cloning a graph.
- Managing auxiliary metadata attached to a specific instance.

In those scenarios, merging two objects simply because `equals` returns `true` would break the algorithm.

### 12.2. IdentityHashMap Is a Specialized Structure

`IdentityHashMap` compares keys by reference rather than by standard object equality. Two keys with different references but the same logical value are kept as two separate mappings.

This is the intentional design of a specialized structure, not a drop-in replacement for `HashMap`. It deliberately departs from the general `Map` contract regarding equality.

Choose it when an algorithm genuinely requires reference identity. Do not use it as a band-aid to hide poorly designed key `equals` or `hashCode` methods.

See [IdentityHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

### 12.3. Object Identity Differs from Business Identity

Two Java objects both representing a product with code `P1` are not necessarily the same instance.

The phrase "same product" may refer to the business identifier, whereas "same object" refers to the reference. When discussing in a team or naming variables, clarify which layer of meaning is under consideration.

## 13. Equality Does Not Prove Whether State Is Shared

### 13.1. Two Value-Equal Objects Can Be Independent

Two immutable objects with the same value can be allocated separately. `equals` returning `true` does not mean that modifying one side would affect the other.

### 13.2. Two Collections with Different References Can Share Elements

`new ArrayList<>(source)` creates a distinct list object but copies the element references.

Two lists can have different references and be equal by content while still sharing the exact same element objects. If the elements are mutable, that shared state relationship must be analyzed separately.

### 13.3. Same Reference Does Not Mean State Is Unchanging Over Time

An object can retain its identity while its internal fields are mutated.

Therefore, `a == b` being `true` at a point in time does not prove that the object is immutable, thread-safe, or safe to mutate arbitrarily while serving as a hash key.

Distinguish three axes:

1. Object identity.
2. Logical equality at the current state.
3. State sharing and mutability.

## 14. A Comparator Returning 0 Does Not Always Mean equals Returns true

When a data structure uses a comparison ordering, there is another relation that must be kept distinct from the two main ones.

For example, a comparator that compares products solely by price may treat two products with different codes as having the same ordering position when their prices are equal.

That does not make the products' `equals` method return `true`.

In `TreeSet` or `TreeMap`, comparison results govern element or key recognition. If you want them to consistently obey the general `Set` or `Map` contract, you must design an ordering that is consistent with `equals`.

Do not carry conclusions from `HashSet` over to a tree using a comparator with different criteria without examining the comparison relation. Likewise, do not use `compare(...) == 0` as a blanket replacement for `equals` across an application.

## 15. Complete Java Program

The program below compares identity with logical equality across three levels: standalone objects, elements inside collections, and container structures themselves.

Save as `ReferenceAndValueEqualityDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;

public class ReferenceAndValueEqualityDemo {
    static final class PlainProduct {
        private final String code;

        PlainProduct(String code) {
            this.code = code;
        }
    }

    static final class Product {
        private final String code;
        private final String label;

        Product(String code, String label) {
            this.code = Objects.requireNonNull(code);
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product that)) {
                return false;
            }
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }

        @Override
        public String toString() {
            return code + ":" + label;
        }
    }

    public static void main(String[] args) {
        String text1 = new String("java");
        String text2 = new String("java");
        System.out.println("String same reference: " + (text1 == text2));
        System.out.println("String same value: " + text1.equals(text2));

        PlainProduct plain1 = new PlainProduct("P1");
        PlainProduct plain2 = new PlainProduct("P1");
        System.out.println("Default equals: " + plain1.equals(plain2));

        Product p1 = new Product("P1", "Pen");
        Product p2 = new Product("P1", "Blue pen");
        Product alias = p1;
        System.out.println("Alias same reference: " + (p1 == alias));
        System.out.println("Products same reference: " + (p1 == p2));
        System.out.println("Products same value: " + p1.equals(p2));
        System.out.println("Equal hash codes: "
                + (p1.hashCode() == p2.hashCode()));

        List<Product> products = new ArrayList<>(List.of(p1));
        System.out.println("List contains equal product: "
                + products.contains(p2));
        System.out.println("List removes equal product: "
                + products.remove(p2));

        Set<Product> distinct = new HashSet<>(List.of(p1, p2));
        System.out.println("HashSet size: " + distinct.size());

        Map<Product, Integer> normalMap = new HashMap<>();
        normalMap.put(p1, 10);
        normalMap.put(p2, 20);
        System.out.println("HashMap size: " + normalMap.size());
        System.out.println("HashMap value: " + normalMap.get(p1));

        Map<Product, Integer> identityMap = new IdentityHashMap<>();
        identityMap.put(p1, 10);
        identityMap.put(p2, 20);
        System.out.println("IdentityHashMap size: " + identityMap.size());

        List<String> left = new ArrayList<>(List.of("A", "B"));
        List<String> right = new LinkedList<>(List.of("A", "B"));
        System.out.println("Lists same reference: " + (left == right));
        System.out.println("Lists same value: " + left.equals(right));

        Set<String> set1 = new HashSet<>(List.of("A", "B"));
        Set<String> set2 = new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("Sets same value: " + set1.equals(set2));

        Queue<String> queue1 = new ArrayDeque<>(List.of("A", "B"));
        Queue<String> queue2 = new ArrayDeque<>(List.of("A", "B"));
        System.out.println("ArrayDeque equals: " + queue1.equals(queue2));

        int[] array1 = {1, 2};
        int[] array2 = {1, 2};
        System.out.println("Array equals: " + array1.equals(array2));
        System.out.println("Array content equality: "
                + Arrays.equals(array1, array2));

        Object[] nested1 = {new int[]{1, 2}};
        Object[] nested2 = {new int[]{1, 2}};
        System.out.println("Nested array shallow equality: "
                + Arrays.equals(nested1, nested2));
        System.out.println("Nested array deep equality: "
                + Arrays.deepEquals(nested1, nested2));

        System.out.println("Objects.equals with nulls: "
                + Objects.equals(null, null));
    }
}
```

Compile and run:

```shell
javac --release 17 ReferenceAndValueEqualityDemo.java
java ReferenceAndValueEqualityDemo
```

Expected output:

```text
String same reference: false
String same value: true
Default equals: false
Alias same reference: true
Products same reference: false
Products same value: true
Equal hash codes: true
List contains equal product: true
List removes equal product: true
HashSet size: 1
HashMap size: 1
HashMap value: 20
IdentityHashMap size: 2
Lists same reference: false
Lists same value: true
Sets same value: true
ArrayDeque equals: false
Array equals: false
Array content equality: true
Nested array shallow equality: false
Nested array deep equality: true
Objects.equals with nulls: true
```

### 15.1. Why Are PlainProduct Instances Not Equal?

Both objects have the same `code` field, but the class does not override `equals`. They continue to use `Object`'s default reference equality.

The program deliberately avoids relying on `toString` or hash codes of these objects to infer the result.

### 15.2. Why Are Product Instances Equal Even Though Their Labels Differ?

The `Product` class selects `code` as its equality criterion and computes its hash code from that same field. The label is merely a descriptive attribute in this example model.

`p1` and `p2` are created by two separate `new` calls, so they have different references. `alias` receives its value from assigning `p1`, so it shares the exact same reference as `p1`.

### 15.3. Why Do contains, remove, Set, and Map React That Way?

The list can find and remove a value-equal object via `p2`.

The hash set merges two equal values into a single element. The standard hash map manages one mapping; the value after the second write is `20`.

The identity map retains two keys because the two objects are distinct instances.

### 15.4. Why Not Print the Contents of HashSet or IdentityHashMap as Expected Output?

The example observes sizes and queried values so it does not depend on the unguaranteed iteration order of those structures.

Choosing deterministic output ensures the experiment proves the exact relation being studied, rather than accidentally teaching an order that happens to appear in a single run.

### 15.5. Why Are ArrayDeque Instances Not Equal Despite Having the Same Elements?

The content equality of `List` is not an automatic rule for every collection. `ArrayDeque` does not implement element-sequence `equals` like a list.

For arrays, you must choose `Arrays.equals` or `Arrays.deepEquals` according to the structure being compared.

## 16. How to Choose a Comparison Operation in Production Code

| Question | Approach |
| --- | --- |
| Do two variables point to the same instance? | Appropriate reference comparison with `==` |
| Do two strings have the same content? | `String.equals`, or a dedicated collation/matching operation as required |
| Are two potentially null values equal according to their class? | `Objects.equals` |
| Do two domain objects satisfy the same value criteria? | Design and use a contract-compliant `equals` |
| Do two lists contain the same sequence of elements? | `List.equals` contract |
| Do two sets contain the same members? | `Set.equals` contract with consistent elements and structure |
| Do two standard maps contain the same mappings? | `Map.equals` contract |
| Do two one-dimensional arrays have the same content? | Appropriate `Arrays.equals` overload |
| Do two object arrays containing nested arrays have the same deep content? | `Arrays.deepEquals` according to its contract |
| Does the algorithm need to distinguish instances that have the same value? | An identity-based structure chosen deliberately |

Always check the exact types in play: `Objects.equals` does not automatically apply list rules to a deque, and `Arrays.deepEquals` does not automatically understand arbitrary business relations inside custom classes.

## 17. Common Pitfalls and How to Diagnose Them

### 17.1. equals Always Returns false for Objects with the Same Data

Check whether the class properly overrides `equals(Object)` or merely overloads it with a specific type. Use `@Override` and inspect the comparison criteria.

### 17.2. contains or get Cannot Find a Newly Recreated Key

Check simultaneously:

- Does `equals` consider the query object equal to the stored object?
- Is `hashCode` consistent with `equals`?
- Was any field used in comparison or hashing mutated after insertion?
- Is the structure comparing by a comparator or by reference identity?

Do not jump to the conclusion that the collection is broken.

### 17.3. A Set Has Fewer Elements Than the Number of Additions

The added elements may be considered equal. Inspect the input data and the equality criteria.

If you genuinely need to keep every occurrence, a list or a frequency-counting model may be more appropriate. Do not corrupt `equals` to force a set to hold values that it is supposed to treat as duplicates.

### 17.4. Two Objects Print Identically but Are Not Equal

`toString` is a display representation, not a binding definition of equality. Inspect the class contract and the actual method being called.

### 17.5. Two Lists Containing Arrays Produce Unexpected Results

Trace from the outside in: the list compares element by element; what equality does the array element use? Do you need an explicit array content comparison instead?

### 17.6. Using == on Wrappers Because of Caching

Some wrapper values share cached objects, causing reference comparisons to return `true`. That is not a valid basis for choosing `==` for general value equality.

The issue is fixed by choosing the right comparison relation, not by memorizing cache ranges.

## 18. Self-Check Exercises

### Exercise 1: Draw the Reference Graph

Create an object, assign it to two variables, then reassign one variable to a newly created object with the same data.

Draw the before and after states. Predict `==` and `equals` first for a class with default equality, and then for a class with code-based equality.

### Exercise 2: Design Equality for Two Data Types

One type represents a coordinate point; the other represents a customer with a stable ID and a mutable name.

Choose the attributes that should participate in equality for each type, explain why, and write a consistent `hashCode`. Do not assume the same formula fits both models.

### Exercise 3: Distinct References as Collection Elements

Create two objects that are equal by value but have different references. Use them with `ArrayList`, `HashSet`, `HashMap`, and `IdentityHashMap`.

Predict `contains`, element counts, or mapping counts before running. Explain which relation each data structure uses.

### Exercise 4: Multi-Level Comparisons

Test the following pairs:

- Two lists `[A, B]` of different implementation classes.
- Two lists `[A, B]` and `[B, A]`.
- Two sets with the same elements added in different orders.
- Two separate `int[]` arrays with the same content.
- Two lists containing two separate arrays with the same content.

Do not just record the output; specify which method is invoked at the container level and at the element level.

### Exercise 5: Verify the equals Contract

For a custom class you wrote, test:

- The same object.
- Distinct objects with matching criteria.
- Objects differing in at least one deciding attribute.
- `null`.
- An object of an incompatible type.
- Swapping the comparison order.
- Three objects to verify transitivity.
- Two equal objects producing the same hash code.

Do not test that two unequal objects must have different hash codes, because that is not required by the contract.

### Exercise 6: Sharing vs. Equality

Create a shallow copy of a list containing mutable elements. Observe:

- Do the two lists share the same reference?
- Are they equal as lists?
- Do corresponding elements share the same reference?
- When a shared element is mutated, which side sees the change?

This exercise forces you to separate content equality from data-sharing relationships.

## 19. Conclusions to Avoid

- "If the printed data looks the same, `==` must be `true`."
- "`equals` always compares every field."
- "The default `equals` automatically compares attribute values."
- "If two objects are equal, they must be the same instance."
- "If two hash codes are equal, the two objects are equal."
- "`identityHashCode` is a memory address or an absolutely unique identifier."
- "Every collection implements content-based `equals` like `List`."
- "A record or a list automatically turns internal arrays into deep comparisons."
- "`Objects.equals` automatically fixes a broken `equals` contract."
- "Having the same reference proves the object cannot change."

The right approach starts with stating clearly which relation needs to be checked: instance identity, model equality, container equality, or ordering equivalence. Once these layers of meaning are separated, searching, deduplication, hashing, and collection comparison behaviors can be explained by contracts rather than guesswork.
