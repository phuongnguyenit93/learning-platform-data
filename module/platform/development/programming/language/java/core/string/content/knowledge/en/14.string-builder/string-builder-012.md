# StringBuilder: `equals`, `compareTo`, and Multi-Thread Sharing Limitations

`StringBuilder` is a **mutable string** class in Java. It is well suited for creating or editing text via `append`, `insert`, `replace`, and `delete` without creating a new `String` value for each concatenation. However, mutability brings three issues you must distinguish: **object comparison with `equals`**, **ordered content comparison with `compareTo`**, and **safety under concurrent multi-threaded access**.

The most important points:

- `StringBuilder` **does not override `Object.equals(Object)`**. Two separate builders, even with identical content, are not equal under `equals`.
- On Java 11 and later, `StringBuilder` provides `compareTo(StringBuilder)` to **compare content in lexicographic order**. Two different builder objects with the same content return `0`.
- `StringBuilder` **provides no synchronization for concurrent access**. If a mutable builder is shared across multiple threads, the program must establish explicit synchronization and clear ownership rules.

This is not a contradiction in Java: `equals` and `compareTo` implement **two different contracts**, while thread safety depends on how reads and writes are coordinated.

## 1. How Does `StringBuilder` Differ from `String`?

| Criterion | `String` | `StringBuilder` |
| --- | --- | --- |
| Text data | Immutable after creation | Can append, delete, and replace characters |
| Used for | Text values, comparison keys, API arguments | Building/editing text in one place |
| `equals(Object)` | Compares content of two `String`s | Inherits `Object.equals`: compares reference identity |
| `compareTo(...)` | Lexicographic comparison of two `String`s | Lexicographic comparison of two `StringBuilder`s on Java 11+ |
| `hashCode()` | Content-based | Inherits `Object.hashCode`: not a content-based hash code |
| Sharing across threads | Immutable value convenient to share after safe publication | Requires protection when threads may read/write concurrently |

For example, `StringBuilder sb = new StringBuilder("Java");` creates a builder with initial content `Java`; `sb.append(" Core")` mutates that builder itself into `Java Core`. This behaves differently from `String`: calling `text.concat(" Core")` does not mutate `text`, instead returning a corresponding string value for the caller to use.

A `StringBuilder` is **not** a `String`: even though both hold text, you cannot pass a builder directly into every API expecting `String`. When you need a `String` value for content comparison or passing onward, use `sb.toString()`.

## 2. `StringBuilder.equals(Object)` Is Identity Comparison

Unlike `String`, `StringBuilder` **does not override `equals(Object)`**. It inherits `Object`'s behavior: the method returns `true` only when the compared object is **the exact same object**.

```java
StringBuilder first = new StringBuilder("Java");
StringBuilder second = new StringBuilder("Java");
StringBuilder alias = first;

System.out.println(first == second);       // false
System.out.println(first.equals(second));  // false
System.out.println(first == alias);        // true
System.out.println(first.equals(alias));   // true
```

The snippet above is illustrative code placed inside a Java method. Both `first` and `second` are independently created builders, so their references differ; `alias` is simply another reference pointing to `first`'s object.

If you want to compare the **content** of two builders, do not call `first.equals(second)` expecting it to behave like `String.equals`. You can create two immutable `String` values:

```java
boolean sameText = first.toString().equals(second.toString());
```

The result is `true` if the contents are equal at the moment each value is captured. If multiple threads are mutating the builders, synchronization is required to obtain a consistent snapshot; `toString()` itself does not make all builder operations thread-safe.

### Complete Experiment

File `BuilderEqualityDemo.java`:

```java
public class BuilderEqualityDemo {
    public static void main(String[] args) {
        StringBuilder a = new StringBuilder("abc");
        StringBuilder b = new StringBuilder("abc");
        StringBuilder same = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(same): " + a.equals(same));
        System.out.println("strings equal: " +
                a.toString().equals(b.toString()));
        System.out.println("builder equals String: " +
                a.equals("abc"));

        a.append('!');
        System.out.println("after append: " + a);
        System.out.println("alias sees change: " + same);
        System.out.println("now strings equal: " +
                a.toString().equals(b.toString()));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 BuilderEqualityDemo.java
java BuilderEqualityDemo
```

Output:

```text
a == b: false
a.equals(b): false
a.equals(same): true
strings equal: true
builder equals String: false
after append: abc!
alias sees change: abc!
now strings equal: false
```

`a.equals("abc")` also returns `false` because the argument is a `String`, not the same object as `a`. `alias` points to `a`, so it sees the change when `a.append('!')` is called.

## 3. `compareTo(StringBuilder)`: Lexicographic Content Comparison

Since **Java 11**, `StringBuilder` implements `Comparable<StringBuilder>` and provides the method:

```java
public int compareTo(StringBuilder another)
```

The method uses **lexicographic order** of the UTF-16 character units in the builders' contents:

- Returns a **negative number** if the left builder's content precedes the right's.
- Returns **`0`** if both UTF-16 code unit sequences have the same content.
- Returns a **positive number** if the left content follows the right's.

Do not check `compareTo(...) == -1` or `== 1` to test ordering. The contract to rely on is the **sign of the result** (`< 0`, `== 0`, `> 0`), not a specific magnitude.

Example:

```java
StringBuilder a = new StringBuilder("apple");
StringBuilder b = new StringBuilder("banana");
StringBuilder c = new StringBuilder("apple");

System.out.println(a.compareTo(b) < 0); // true
System.out.println(b.compareTo(a) > 0); // true
System.out.println(a.compareTo(c) == 0); // true
System.out.println(a.equals(c));         // false
```

`a.compareTo(c) == 0` means **the contents are currently equal**, not that `a` and `c` are the same object. For this exact reason, the Java API warns that **this natural ordering is inconsistent with `equals`** (`natural ordering inconsistent with equals`).

### Demonstrative Program with Verifiable Output

File `BuilderComparisonDemo.java`:

```java
public class BuilderComparisonDemo {
    public static void main(String[] args) {
        StringBuilder left = new StringBuilder("apple");
        StringBuilder right = new StringBuilder("banana");
        StringBuilder sameText = new StringBuilder("apple");

        System.out.println("left < right: " +
                (left.compareTo(right) < 0));
        System.out.println("right > left: " +
                (right.compareTo(left) > 0));
        System.out.println("left.compareTo(sameText): " +
                left.compareTo(sameText));
        System.out.println("left.equals(sameText): " +
                left.equals(sameText));

        right.setLength(0);
        right.append("apple");
        System.out.println("after change comparison: " +
                left.compareTo(right));
        System.out.println("after change equals: " +
                left.equals(right));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderComparisonDemo.java
java BuilderComparisonDemo
```

Output:

```text
left < right: true
right > left: true
left.compareTo(sameText): 0
left.equals(sameText): false
after change comparison: 0
after change equals: false
```

Calling `right.setLength(0)` clears the builder's effective content, and `append("apple")` writes the text `apple`. The content change causes `compareTo` to return a new value, whereas `equals` remains an identity check and does not change its result because the two objects are still distinct.

There is no default "frozen" content comparison for mutable builders: after any edit, its ordering relative to another builder **can** change.

## 4. `compareTo` Does Not Replace `equals` and Cannot Compare Directly Against `String`

These are distinct operations:

```java
StringBuilder builder = new StringBuilder("hello");
StringBuilder otherBuilder = new StringBuilder("hello");
String stringValue = "hello";

// By object identity:
boolean sameBuilderObject = builder.equals(otherBuilder); // false

// By content ordering of two builders:
boolean sameBuilderContent = builder.compareTo(otherBuilder) == 0; // true

// By String content:
boolean sameAsString = builder.toString().equals(stringValue); // true
```

This is illustrative code inside a method. `compareTo` takes a `StringBuilder`, **not a `String`**. Thus `builder.compareTo(stringValue)` is not type-valid; you must decide whether to compare two builders with `compareTo`, or create a `String` and use `String`'s `equals`/`compareTo`.

To search for a substring, use appropriate text APIs such as `indexOf` (when applicable to the builder) or a `toString()` snapshot, instead of inferring containment from `compareTo`. `compareTo` returns only the **ordering relation between the entire contents of two objects**.

`StringBuilder.compareTo` is also not a natural-language comparator: it relies on UTF-16 code unit order and is case-sensitive. If you need to sort people's names according to language rules, specify an appropriate locale and text comparator, usually working with immutable `String` values.

## 5. Why Do `HashSet` and `TreeSet` Handle Same-Content Builders Differently?

The inconsistency between `equals` and `compareTo` has consequences when using collections:

- `HashSet` determines duplicates using `hashCode` and `equals`. `StringBuilder` does not override those two methods to be content-based, so **two distinct builder objects** are two distinct elements.
- `TreeSet` with natural ordering determines equivalence using **`compareTo(...) == 0`**. Two builders with identical content can be treated as a single element in the set even though their `equals` returns `false`.

File `BuilderSetDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BuilderSetDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("x");
        StringBuilder second = new StringBuilder("x");

        Set<StringBuilder> hash = new HashSet<>();
        hash.add(first);
        hash.add(second);

        Set<StringBuilder> sorted = new TreeSet<>();
        sorted.add(first);
        sorted.add(second);

        System.out.println("equals: " + first.equals(second));
        System.out.println("compareTo zero: " +
                (first.compareTo(second) == 0));
        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + sorted.size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BuilderSetDemo.java
java BuilderSetDemo
```

Output:

```text
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
```

The difference is **not a random bug** in collections; it comes from `StringBuilder`'s comparison contract. `SortedSet` and `SortedMap` rely on ordering to define equivalence, so using a type whose natural ordering is inconsistent with `equals` can produce behavior opposite to a developer's expectations.

**Do not use mutable builders as keys for sorting or content-based identification.** If you need a set of unique strings by content, the natural choice is converting to `String`:

```java
Set<String> texts = new HashSet<>();
texts.add(first.toString());
texts.add(second.toString()); // Same content, HashSet keeps one value

System.out.println(texts.size()); // 1
```

This snippet belongs inside a method with `java.util.Set` and `java.util.HashSet` imported. `String` has content-based `equals`/`hashCode` and is immutable, making it far better suited as a text key in sets and maps.

## 6. A Mutable Builder Is Not a Stable Sort Key

Suppose a `TreeSet<StringBuilder>` sorted builder contents at insertion time. Later, one builder is mutated from `"a"` to `"z"`. The search tree **does not automatically re-sort** when an element's content changes in place. Subsequent `contains`, `remove`, or ordered iteration operations may no longer reflect the ordering invariant assumed by the data structure.

That is why you should not insert a builder and then continue calling `append` or `delete` on that same object as a key:

```java
// Illustrates a DESIGN TO AVOID:
TreeSet<StringBuilder> values = new TreeSet<>();
StringBuilder key = new StringBuilder("abc");
values.add(key);
key.append("xyz"); // Modifies the key after insertion into TreeSet
```

This snippet requires importing `java.util.TreeSet` and belongs inside a method; you should not infer a fixed deterministic lookup result after mutating the key. The problem is that **the structure's ordering invariant can be broken**.

A safer approach is using an immutable `String` snapshot right when adding to the set:

```java
TreeSet<String> values = new TreeSet<>();
StringBuilder input = new StringBuilder("abc");

values.add(input.toString());
input.append("xyz");

System.out.println(values.contains("abc"));    // true
System.out.println(values.contains("abcxyz")); // false
```

Because the set stores the string captured at `add` time, mutating `input` afterward does not alter the key inside `TreeSet`.

## 7. `StringBuilder` Is Not Synchronized for Multiple Threads

According to the Java documentation, `StringBuilder` is designed for use when string-building operations **do not require synchronization**. It fits **single-threaded** code or a builder exclusively owned by a single processing unit, reducing synchronization overhead compared to `StringBuffer` in those scenarios.

However, `StringBuilder` is mutable. If **the same object** is mutated by multiple threads calling `append`/`delete`/`insert`/`setCharAt`, or one thread writes while another reads content without a proper synchronization relationship, a **data race** can occur:

- Updates from one thread may not be observed as expected by another thread.
- Interleaved operations can cause **lost data, wrong ordering, or unexpected intermediate states**.
- Reading `length()`, `charAt()`, `toString()`, or `compareTo()` while another thread mutates the builder does not automatically guarantee a consistent snapshot.
- There is no guaranteed specific result or fixed exception: an unsynchronized program might *appear to work* across many runs yet still be unsafe.

**Having two threads in a program does not make every builder dangerous.** The issue arises when threads **access the same mutable object with at least one write** without coordination under the Java Memory Model. If each thread owns its own builder, no mutable builder is shared and that risk does not arise.

### Do Not Treat `append` as Atomic When Shared

The following is unsafe to rely on in a multi-threaded program:

```java
// Illustrates behavior TO AVOID: shared across threads.
StringBuilder shared = new StringBuilder();

Runnable action = () -> {
    for (int i = 0; i < 1000; i++) {
        shared.append('X');
    }
};
```

This is an illustrative fragment, not a complete program. If two threads execute `action` concurrently **without locking**, there is no guarantee the result always has exactly 2000 characters. You should not attach a fixed "sample stdout" for a program with a data race, because output depends on execution and can vary from run to run.

## 8. Safe Example: A Shared Lock Protecting Every Operation on the Builder

One valid coordination approach is protecting every **read and write** on the same builder with **the same lock object** via `synchronized`. When you need to extract the result for use outside the locked region, create an immutable `String` inside the protected block.

File `SynchronizedBuilderDemo.java`:

```java
public class SynchronizedBuilderDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuilder shared = new StringBuilder();
        Object lock = new Object();

        Runnable addA = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    shared.append('A');
                }
            }
        };

        Runnable addB = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    shared.append('B');
                }
            }
        };

        Thread first = new Thread(addA);
        Thread second = new Thread(addB);

        first.start();
        second.start();
        first.join();
        second.join();

        String snapshot;
        synchronized (lock) {
            snapshot = shared.toString();
        }

        long countA = snapshot.chars().filter(c -> c == 'A').count();
        long countB = snapshot.chars().filter(c -> c == 'B').count();

        System.out.println("length=" + snapshot.length());
        System.out.println("countA=" + countA);
        System.out.println("countB=" + countB);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SynchronizedBuilderDemo.java
java SynchronizedBuilderDemo
```

Output:

```text
length=2000
countA=1000
countB=1000
```

The order of `'A'`/`'B'` characters **is not fixed** because the two threads can acquire the lock in different orders. Yet every `append` is protected by the same lock and both threads finish before taking the snapshot, so **the total length and per-character counts** are deterministic as shown above.

`synchronized(lock)` is a straightforward coordination mechanism. Crucially, **all code paths accessing the mutable builder must follow the same synchronization convention**, including reads. Locking only some writes while letting other code read or write freely provides no complete guarantee.

## 9. If You Only Need to Send the Result to Another Thread, Capture an Immutable `String`

Most applications do not need to share a mutable builder for multiple threads to edit together. A more manageable pattern:

1. Create `StringBuilder` as a local variable in one method/thread.
2. Use it to assemble the text.
3. Call `toString()` to obtain an immutable value.
4. Pass the `String` result to other components/threads using a proper publication mechanism.

Example:

File `BuilderSnapshotDemo.java`:

```java
public class BuilderSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Hi");
        String snapshot = builder.toString();

        builder.append(" there");

        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);
        System.out.println("equalContents=" +
                builder.toString().equals(snapshot));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
```

Output:

```text
builder=Hi there
snapshot=Hi
equalContents=false
```

`snapshot` is not a "live window" into the builder. It preserves the string value at the time `toString()` was called. If the builder changes content afterward, `snapshot` does not change.

An immutable `String` itself is convenient to share; however, an application still needs a **proper reference transfer/publication mechanism** in multi-threaded designs (such as `Thread.start`, `Future` task results, concurrent queues, `volatile`, or synchronization as appropriate). Do not use immutability as an excuse to ignore Java Memory Model publication rules entirely.

## 10. What Does `StringBuffer` Help With, and Where Are Its Limits?

`StringBuffer` is a mutable class similar to `StringBuilder` whose main methods are synchronized. When you genuinely need a shared buffer with method-level synchronized operations, `StringBuffer` can be an appropriate choice.

However, **synchronizing individual methods does not make an entire sequence of actions atomic**. Logic example:

```java
// Illustrates NON-ATOMIC logic:
if (buffer.length() < 100) {
    buffer.append("data");
}
```

If `buffer` is a `StringBuffer` and multiple threads execute concurrently, one thread can read the length while another mutates the content before the subsequent `append`. To make both steps (**check + update**) a single unified transaction, protect them with a single synchronized block or redesign the processing structure.

You can coordinate externally:

```java
synchronized (buffer) {
    if (buffer.length() < 100) {
        buffer.append("data");
    }
}
```

This is an illustrative fragment inside a method with `buffer` already declared. When using external locking, every participant in the composite operation must follow a consistent convention.

Also, do not interpret "`StringBuffer` is synchronized" as "every multi-threaded usage pattern always produces business-correct content". **Per-operation thread safety** and **atomicity of an entire workflow** are two different levels of guarantee.

## 11. Comparing When a Builder Is Concurrently Modified

A program can avoid racing `append` calls by having only one writer thread, yet still fail when a **reader thread** calls `compareTo` or `toString()` without coordinating with the writer thread.

Suppose:

- Thread A is modifying `StringBuilder orderCode`.
- Thread B calls `orderCode.compareTo(expected)` to decide whether it matches.

Without proper synchronization/happens-before, Thread B is not guaranteed to observe consistent content. The fact that `compareTo` itself only reads does not make the whole object thread-safe. Never build validation logic or security checks on top of a snapshot that can be updated concurrently.

Design patterns worth considering:

- Convert content to an immutable `String` under synchronization and compare snapshots.
- Give **only one thread ownership** of the builder; other threads communicate via immutable messages/values.
- If a shared builder must truly be accessed concurrently, use consistent locking across reads, writes, and comparisons.
- When merely joining independent segments, let each thread build its own segment and combine results in one place.

This is a limitation of **mutable object access**, not a flaw specific to `equals` or `compareTo`.

## 12. Notes on Unicode and Ordering with `compareTo`

`StringBuilder` stores a sequence of UTF-16 code units. The lexicographic ordering of `compareTo` is based on **UTF-16 code units**; it is neither the natural dictionary order of every language nor aware of grapheme cluster segmentation.

Upper/lowercase example:

```java
StringBuilder upper = new StringBuilder("A");
StringBuilder lower = new StringBuilder("a");

System.out.println(upper.compareTo(lower) < 0); // true
System.out.println(upper.compareTo(lower) == 0); // false
```

Because the code units of `A` and `a` differ, the result is non-zero. `compareTo` also does not strip accents, normalize Unicode, or apply a specific `Locale`.

When you need **user-facing text sorting**, identify language and display requirements first; you can convert the builder to `String` and use `java.text.Collator` with an appropriate locale, or another normalization/collation solution as required. When you only need to check identical UTF-16 content, `a.compareTo(b) == 0` is an accurate expression for two single-threaded/stable builders, though it does not turn the builder's `equals` into a content comparison.

## 13. Common Mistakes

**Mistake 1 — Using `a.equals(b)` to compare two `StringBuilder`s with the same content.** `StringBuilder` inherits `Object.equals`, so two different objects return `false`. Use `compareTo(b) == 0` when both are builders, or capture `String`s and compare content.

**Mistake 2 — Interpreting `compareTo(b) == 0` as `a.equals(b) == true`.** For builders, the two expressions are **not equivalent**. A builder's natural ordering is documented as inconsistent with `equals`.

**Mistake 3 — Assuming `HashSet<StringBuilder>` deduplicates equal text values.** `HashSet` uses the builder object's `hashCode` and `equals`; two builders with the same content remain two distinct elements.

**Mistake 4 — Assuming `TreeSet<StringBuilder>` and `HashSet<StringBuilder>` have the same duplicate semantics.** `TreeSet` uses natural ordering, so two builders with `compareTo == 0` are treated as equivalent, contrary to `equals`.

**Mistake 5 — Mutating a builder after using it as a key in `TreeSet` or `TreeMap`.** Changing content can break the ordering invariant; convert to immutable `String` before using as a key.

**Mistake 6 — Using a shared `StringBuilder` across multiple threads calling `append` without synchronization.** This is a data race; you cannot rely on correct results even if a few test runs show no error.

**Mistake 7 — Locking only the writer thread while letting other threads freely read or compare.** Reading/capturing a snapshot must also participate in the synchronization protocol if the same builder is being mutated.

**Mistake 8 — Thinking `StringBuffer` makes a check-then-update sequence atomic.** Synchronized individual methods do not make multi-method combinations atomic.

**Mistake 9 — Using `compareTo` to sort Vietnamese or natural-language text without considering locale.** `compareTo` compares UTF-16 code units, not language-specific collation.

**Mistake 10 — Keeping a mutable builder shared when you only need to send a text result.** Creating a `String` snapshot is usually simpler and safer, alongside proper reference publication across threads.

## 14. Self-Check Questions

**Question 1.** Given two separate builders both containing `"java"`, what do `equals` and `compareTo` return?

**Answer:** `a.equals(b)` is `false` because they are different objects, whereas `a.compareTo(b) == 0` is `true` because they have the same content.

**Question 2.** Why can `HashSet<StringBuilder>` contain two builders with the same text while `TreeSet<StringBuilder>` keeps only one?

**Answer:** `HashSet` uses `Object.equals`/`hashCode` by builder identity; `TreeSet` uses `compareTo` by content to determine equivalence.

**Question 3.** Should you mutate a builder's content after inserting it into a `TreeSet`?

**Answer:** No. Element ordering relies on the content at insertion time, and the tree does not automatically re-sort when you mutate the builder. Use immutable `String` keys.

**Question 4.** Are two threads concurrently calling `append` on one `StringBuilder` guaranteed not to lose data?

**Answer:** No. Operations on `StringBuilder` are unsynchronized; avoid sharing mutable builders or use appropriate locking/coordination for all related accesses.

**Question 5.** Does `StringBuffer` guarantee that `length()` followed by `append()` is always atomic?

**Answer:** No. Per-method synchronization does not merge two calls into one transaction. To make "check-then-update" atomic, coordinate externally or use a different structure.

**Question 6.** If you call `String snapshot = builder.toString();` and then `builder.append("!");`, does the content of `snapshot` change?

**Answer:** No. `snapshot` is an immutable `String` holding the content at the time it was created; it does not reference the builder as a mutable view.

**Key takeaway:** `StringBuilder.equals` compares **identity**, `StringBuilder.compareTo` (Java 11+) compares **lexicographic content**, and these two contracts are inconsistent with each other. `StringBuilder` is **mutable and unsynchronized**: prefer single-thread ownership, use `String` snapshots when sharing values, and protect all shared accesses with consistent synchronization if multi-threading is genuinely needed.
