# Adding Two Equal Objects to a `HashSet` in Java

When inserting two objects that are **different instances but equal by value** into a `HashSet`, the set keeps only **one element** — **if** the object's class properly implements the `equals()` and `hashCode()` contract. The first addition typically returns `true`; adding the second object, which is considered a duplicate element, returns `false`. This is the core behavior of a **set**: containing no duplicate elements according to its equality criterion.

However, the answer depends on the specific meaning of the word **"equal"**. Two objects with the same content do not necessarily have `equals()` return `true`, and even if `equals()` returns `true`, a contract-violating `hashCode()` can still cause `HashSet` to accept both. This lesson analyzes each case, along with runnable Java 17 examples.

## 1. Standard Result When Two Objects Are Equal

Suppose we have two instances of the same type, with the same values:

~~~java
Book first = new Book("978-1", "Java");
Book second = new Book("978-1", "Java");
~~~

This is an **illustrative snippet**; the complete `Book` definition appears in the program below.

The two variables `first` and `second` are created with two separate `new` calls, so `first == second` is `false`. If `Book.equals()` compares the two fields `isbn` and `title`, then `first.equals(second)` is `true`. When adding them to the same `HashSet<Book>`:

~~~java
Set<Book> books = new HashSet<>();
System.out.println(books.add(first));  // true
System.out.println(books.add(second)); // false
System.out.println(books.size());      // 1
~~~

The two snippets above can be placed inside `main` with appropriate imports and the `Book` definition. They illustrate three key points:

- **`add(first) == true`:** the set does not yet contain any element equivalent to `first`, so adding succeeds.
- **`add(second) == false`:** the set already contains an element equivalent to `second`, so no logical duplicate is added.
- **`size() == 1`:** there is only one distinct element according to the equality rule, even though two instances were created.

The duplicate addition does not increase `size()` and **does not replace the existing instance with the passed-in instance**. `HashSet` is not a store of all instances, nor does it automatically merge attributes from two equivalent objects.

## 2. "Equal" Does Not Mean `==`

For variables of **reference** types:

| Check | Meaning | Two different instances with the same content |
|---|---|---|
| `first == second` | Do both variables point to the same object? | `false` |
| `first.equals(second)` | Are the two objects equal by the type's definition? | Can be `true` |
| `first.hashCode() == second.hashCode()` | Do the two objects have matching hash codes? | **Must be `true` if equals is true** |
| `books.add(second)` | Is a new, non-duplicate element added? | `false` when the set already has an equivalent element and the contract is followed |

The default `Object.equals()` only considers two references pointing to the same instance as equal. A custom class that **does not** override `equals()` inherits that default meaning; in that case, two `new` calls even with identical data are usually treated as two distinct elements by `HashSet`.

`String`, common wrapper types, `BigInteger`, many value objects, and Java `record`s define equality by content. A `record` automatically generates `equals()` and `hashCode()` from its components. **A `record` does not automatically deep-compare elements of an array component**: if a component is an array, the array's default equality remains reference-based unless the developer handles it explicitly.

## 3. The Cooperative Role of `hashCode()` and `equals()`

`HashSet` is implemented on top of a hash structure (`HashMap` in standard JDKs). When adding a non-`null` element, the set uses `hashCode()` to route to a storage/search region, and then uses `equals()` to determine an equivalent key when needed.

You can picture it as:

1. Compute the hash of the object to be added.
2. Determine the position/bucket corresponding to the hash under the current internal organization.
3. Check in the appropriate position whether a duplicate element by equality already exists.
4. If **a duplicate element already exists**, `add` returns `false`; if **none exists yet**, record the new element and return `true`.

This is a **conceptual model** for understanding behavior, not a promise that every JDK version always uses a fixed number of buckets or a fixed method-call order. Policies for computing buckets, handling collisions, or switching to a tree structure under heavy collisions can be implementation details.

Mandatory contract:

> If `a.equals(b)` is `true` then `a.hashCode() == b.hashCode()` **must** hold.

The converse is **not true**: if hashes are the same, `a` and `b` can still be different. Collisions are normal; `HashSet` does not reject an element merely because `hashCode()` matches, but must compare equality appropriately.

If you override `equals()` yet **forget** to override `hashCode()` accordingly, the set can store multiple objects that the application considers equal. That outcome is a consequence of **the class violating the contract**, not a normal rule of `HashSet`.

## 4. Complete Java 17 Example: Valid Case, Broken Hash, Collision, and Mutable Key

Save the following program to **`HashSetEqualityDemo.java`**. It contains four independent scenarios:

- `Book` is a `record`, with valid equality/hash based on both components.
- `BrokenKey` is **intentionally written wrong**: `equals` checks `id` while hash uses `salt`. Used only to demonstrate the bug.
- `CollidingKey` always returns the same hash `7` while equality still distinguishes `id`; this is a **valid** collision.
- `MutableKey` has a field used for hashing that can mutate; the example illustrates why you must not modify a key after adding it to a set.

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class HashSetEqualityDemo {

    record Book(String isbn, String title) {}

    static final class BrokenKey {
        private final String id;
        private final int salt;

        BrokenKey(String id, int salt) {
            this.id = id;
            this.salt = salt;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey b
                    && Objects.equals(id, b.id);
        }

        @Override
        public int hashCode() {
            return salt; // WRONG: equals does not compare salt.
        }
    }

    record CollidingKey(String id) {
        @Override
        public int hashCode() {
            return 7; // Valid: equal objects still have the same hash.
        }
    }

    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int newId) {
            this.id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey m && id == m.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Book first = new Book("978-1", "Java");
        Book equalBook = new Book("978-1", "Java");
        Book differentBook = new Book("978-2", "Concurrency");

        Set<Book> books = new HashSet<>();
        System.out.println("same reference: " + (first == equalBook));
        System.out.println("equal value: " + first.equals(equalBook));
        System.out.println("equal hash: "
                + (first.hashCode() == equalBook.hashCode()));
        System.out.println("add first: " + books.add(first));
        System.out.println("add equal: " + books.add(equalBook));
        System.out.println("size after equal: " + books.size());
        System.out.println("add different: " + books.add(differentBook));
        System.out.println("size after different: " + books.size());
        System.out.println("contains equal copy: "
                + books.contains(new Book("978-1", "Java")));

        BrokenKey brokenA = new BrokenKey("A", 1);
        BrokenKey brokenB = new BrokenKey("A", 2);
        Set<BrokenKey> broken = new HashSet<>();
        System.out.println("broken equals: " + brokenA.equals(brokenB));
        System.out.println("broken same hash: "
                + (brokenA.hashCode() == brokenB.hashCode()));
        System.out.println("broken add A: " + broken.add(brokenA));
        System.out.println("broken add B: " + broken.add(brokenB));
        System.out.println("broken size: " + broken.size());

        Set<CollidingKey> collision = new HashSet<>();
        System.out.println("collision first: "
                + collision.add(new CollidingKey("A")));
        System.out.println("collision different: "
                + collision.add(new CollidingKey("B")));
        System.out.println("collision equal copy: "
                + collision.add(new CollidingKey("A")));
        System.out.println("collision size: " + collision.size());

        MutableKey mutable = new MutableKey(1);
        Set<MutableKey> mutableSet = new HashSet<>();
        mutableSet.add(mutable);
        System.out.println("mutable before: " + mutableSet.contains(mutable));
        mutable.setId(2); // Change both equals/hash after adding to the set.
        System.out.println("mutable after: " + mutableSet.contains(mutable));

        Set<Book> withDuplicates = new HashSet<>(
                List.of(first, equalBook, differentBook));
        System.out.println("from list size: " + withDuplicates.size());
    }
}
~~~

Compile/run with **JDK 17 or higher**:

~~~bash
javac HashSetEqualityDemo.java
java HashSetEqualityDemo
~~~

Output on Java 17:

~~~text
same reference: false
equal value: true
equal hash: true
add first: true
add equal: false
size after equal: 1
add different: true
size after different: 2
contains equal copy: true
broken equals: true
broken same hash: false
broken add A: true
broken add B: true
broken size: 2
collision first: true
collision different: true
collision equal copy: false
collision size: 2
mutable before: true
mutable after: false
from list size: 2
~~~

**Explanation of the results:**

1. The two `Book`s are different instances (`== false`), yet `equals` is `true` and their hashes match. Therefore, the second addition returns `false`; the set contains only one `Book("978-1", "Java")`. `contains` with a **third instance** having the same value also returns `true`.
2. `differentBook` has a different ISBN and title so adding it succeeds, bringing `size` to 2.
3. `BrokenKey`: the two keys have the same ID so `equals` is `true`, yet their hashes are 1 and 2. In this specific case on Java 17, they are placed into different hash positions; both `add` calls return `true` and `size == 2`. This is a **broken implementation**, not a way to achieve duplicate storage functionality.
4. `CollidingKey`: both `"A"` and `"B"` share the same hash yet `equals` is `false`, so they remain two valid elements. Another `"A"` with the same value is rejected. Matching hashes do **not** mean duplicate objects.
5. `MutableKey`: after being added with `id = 1`, the object is changed to `id = 2`. In this Java 17 example, `contains(mutable)` returns `false` because the lookup position for the new hash does not match the original insertion position. Lookup behavior when mutating keys like this is no longer reliable.
6. The constructor accepting a collection `new HashSet<>(List.of(...))` also removes logical duplicates according to valid equality/hash. Only the set creation syntax differs; the duplication rule stays the same.

**Do not rely on element order when printing a `HashSet`:** this set does not guarantee iteration order by insertion order, hash, or ascending order. For example, print boolean values, sizes, and `contains` results rather than printing the entire `HashSet` and asserting a specific order.

## 5. So Does Adding Two Equal Objects "Lose" Data?

What must be distinguished is **instance** vs. **element value**.

~~~java
Book first = new Book("978-1", "Java");
Book second = new Book("978-1", "Java");

Set<Book> books = new HashSet<>();
books.add(first);   // true
books.add(second);  // false
~~~

In this example, `HashSet` stores only one representative for the **equivalence class** of objects that `equals` considers equal. It does not store two duplicate records just to remember that `new` was called twice.

When `add(second)` returns `false`, **the old element stays in the set**; `second` is not used to replace `first`. In the data structure, one element can represent multiple objects equal by the equality rule; a set does not promise to store occurrence counts.

If the problem requires **recording every occurrence**, choose a `List` or an appropriate collection. If you need to **count occurrences**, use a map counting by value, such as `Map<Book, Integer>` with `merge(book, 1, Integer::sum)`. If you need to **choose the new object over the old object**, you must define the replacement logic yourself; `HashSet.add` does not provide that behavior.

## 6. What Happens If Only Data Matches, Without Overriding `equals()`?

Consider a custom class with only a constructor and an `id` field:

~~~java
final class PlainItem {
    private final int id;

    PlainItem(int id) {
        this.id = id;
    }
}
~~~

This is a compilable class definition; it does not contain `main`. When adding `new PlainItem(42)` twice, `PlainItem` inherits `Object.equals()`, which uses identity. Thus, two distinct instances **are not considered equal**, even with the same `id = 42`. A `HashSet<PlainItem>` will typically have size 2 after two additions.

That is **not a bug in `HashSet`**: the class defined its default equality as same-instance identity. If business logic requires two items with the same ID to be one, you must define `equals()` by ID and write a consistent `hashCode()`, or use a value type like a record when appropriate.

Also remember: overriding `equals` on **only a subset of fields** means the remaining fields do not determine duplication. For instance, if `Book.equals()` only checks ISBN, two books with the same ISBN but different descriptive titles are also considered one element. Defining equality is a **data-modeling** decision, not a syntax detail.

## 7. Why Does a Wrong `hashCode()` Cause Two Equal Objects to Coexist?

Suppose:

- `a.equals(b) == true`.
- `a.hashCode() == 1` yet `b.hashCode() == 2`.

This is a direct contradiction with the Java contract. Even though `equals` says they are equal, the hash-based locating step can send them to different regions, resulting in **not checking equality against the already existing element**. The set can then store both `a` and `b`. Depending on collision types, capacity, and implementation, the failure outcome can vary; it must not be used as a guaranteed functional rule.

The fix is:

1. Clearly decide which fields determine whether two objects are equal.
2. Implement `equals()` on those exact fields, obeying reflexivity, symmetry, transitivity, and consistency.
3. Implement `hashCode()` from **the same relevant data** so that every equal pair is guaranteed to have equal hashes. Hashes do not need to be unique.
4. Prefer immutability for fields affecting an element's equality/hash while inside a `HashSet`.
5. Test with an example creating two distinct instances with equal values; verify `equals`, hash code, `add`, `size`, and `contains`.

### Hand-written value class pattern

~~~java
import java.util.Objects;

final class ProductCode {
    private final String code;

    ProductCode(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductCode p)) return false;
        return code.equals(p.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

In this example, `ProductCode` is `final` and `code` is immutable. Two instances with the same `code` are equal and have the same hash; the `instanceof` check is safe from subclasses adding state because **you cannot inherit from a `final` class**. A program using this class needs to provide `main` if you want to run it standalone.

## 8. `null` Cases, Collisions, and Same Reference

### Adding `null` twice

`HashSet` allows **one `null` element**. Starting with an empty set:

~~~java
Set<String> names = new HashSet<>();
System.out.println(names.add(null)); // true
System.out.println(names.add(null)); // false
System.out.println(names.size());    // 1
~~~

This snippet belongs inside `main` and needs `import java.util.Set;` along with `import java.util.HashSet;`. The second `null` does not increase the size. `null.equals(...)` is not called; the structure handles `null` in its own way.

### Adding the exact same instance twice

If `Book book = new Book(...)` and you call `set.add(book)` twice, the results are `true` then `false`. You do not need two separate instances to demonstrate uniqueness; even the exact same reference is not recorded twice. That does not prove that `==` is the set's sole criterion.

### Two different objects with the same hash

There is no requirement that two different objects must have different hash codes. A `hashCode()` that always returns `7` is still contract-compliant in terms of **correctness**, because every equal pair receives 7; however, poor hash distribution causes many collisions, which can hurt performance. `HashSet` still needs `equals()` to distinguish objects that are **not** equal.

## 9. Common Consequences When Using `HashSet`

**Ordering:** `HashSet` makes no commitment regarding iteration order. If you want insertion order, consider `LinkedHashSet`; if you want sorted order, consider `TreeSet`, though `TreeSet` treats `compare(...) == 0` as a duplicate element per the comparator, which can differ from `equals()`.

**Concurrency:** Standard `HashSet` is not automatically synchronized. If multiple threads modify the set concurrently, you need an appropriate coordination mechanism/collection; this is independent of the equality contract.

**Do not mutate fields used as keys:** If an element has already been added and the fields used to compute its hash change, subsequent `contains`, `remove`, or `add` calls can yield unpredictable results. In particular, `equals()` and `hashCode()` being valid at each instant is not enough: key stability **throughout the time it resides in the set** is also crucial.

**Limits of size-based checks:** A set having size 1 after two additions only proves that under the current equality mechanism, the second addition did not create a new element; it does not automatically prove that two objects have identical data by every business criterion. Conversely, size 2 can stem from an unexpected equality definition or a broken hash contract.

## 10. Common Mistakes and Fixes

| Symptom | Possible cause | How to check/fix |
|---|---|---|
| Two objects look alike yet `size == 2` | `equals` not overridden, or `equals` checks extra fields | Print/check `equals`; determine the fields defining value |
| `equals == true` yet both still get added | `hashCode` violates contract | Check hashes of the equal pair; fix hash to be consistent |
| Two different objects with the same hash treated as one | `equals` implemented too broadly or wrongly | Hash collision is **not** enough to deduplicate; fix equality |
| `contains` fails to find an added object | Hash/equality field mutated or contract broken | Use immutable keys; avoid mutating identity fields once added |
| Expecting new element to replace old on duplicate `add` | Misunderstanding `HashSet.add` | `add` returns `false` and keeps the old element |
| Output order differs every time the set is printed | `HashSet` does not guarantee iteration order | Rely only on membership/`size`; pick an ordered collection if needed |
| Assuming a record deep-compares arrays | Array component still uses array equality | Write custom logic to compare element-by-element, or change data structure |

## 11. Self-Check Questions

**Question 1.** `a != b` by reference, `a.equals(b)` is `true`, and both objects have equal hashes. What happens when adding `a` then `b` to an initially empty `HashSet`?  
**Answer:** `add(a)` returns `true`, `add(b)` returns `false`, size is 1.

**Question 2.** Two objects have `hashCode() == 7`, yet `equals() == false`. Can `HashSet` hold both?  
**Answer:** Yes; hash collision does not mean equality. When elements differ by equality and the contract is valid, the set can hold both.

**Question 3.** Two objects are considered equal by the application, yet their `hashCode()` values differ. What should be done?  
**Answer:** Fix the class to obey the contract: equal objects must have the same hash code. Do not rely on incidental behavior of `HashSet` when the contract is violated.

**Question 4.** If `HashSet.add(second)` returns `false`, does the set automatically replace `first` with `second`?  
**Answer:** No. The already existing equivalent element is retained.

**Question 5.** Does using `new HashSet<>(list)` remove logical duplicates in `list`?  
**Answer:** Yes, according to the elements' `equals()`/`hashCode()` definitions and assuming the contract is properly maintained.

**Remember:** Adding two objects that are **equal according to `equals()` and have a valid `hashCode()`** to a `HashSet` retains only one element. Check whether `add` returns `true` or `false`, along with `size()`, instead of relying on `==` or the set's printed order.