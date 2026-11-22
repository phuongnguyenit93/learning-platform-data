# CharSequence Is Not Implicitly Immutable or Content-Equal

## 1. The problem in API design

When writing a string-handling API, it is tempting to choose a `CharSequence` parameter instead of `String` in order to accept multiple data types. For example, a method accepting `CharSequence` can be called with `String`, `StringBuilder`, `StringBuffer`, or `CharBuffer`. This is a strength of interface-based design, but **`CharSequence` does not promise that the object is immutable or that `equals` compares content**.

Two things to remember from the start:

- **Immutability:** `String` is immutable; `StringBuilder` and `StringBuffer` can be mutated, while `CharBuffer` can be a view with mutable position, limit, and backing storage. A parameter declared as `CharSequence` does not freeze the underlying object.
- **Equality:** the `CharSequence` interface does not require implementations to implement `equals`/`hashCode` according to a common equality rule. Two objects with the same `char` sequence can return `equals == false`; the behavior of `equals` depends on the concrete object type.

Therefore, when an API must **store long-term**, **share across threads**, **use as map/set keys**, **cache**, or **check text-based equality**, you need a clear data contract and usually must capture an immutable `String` copy at the API boundary.

## 2. What does the CharSequence interface actually guarantee?

`java.lang.CharSequence` represents **a readable sequence of `char` values**. Its basic operations include:

| Method | Meaning |
| --- | --- |
| `length()` | Number of UTF-16 code units in the current sequence |
| `charAt(index)` | Reads the UTF-16 code unit at the corresponding position |
| `subSequence(start, end)` | Gets a `CharSequence` representing a subsequence |
| `toString()` | Gets the sequence content as a `String` |
| `chars()` and `codePoints()` | Iterates over UTF-16 code units or Unicode code points via `IntStream` |

There is **no** general promise that `length()`, `charAt()`, or the result of `subSequence()` remains immutable over time. `subSequence()` may return a **view sharing data** with the original object; other types may return a copy. An API using `CharSequence` must take that into account.

`length()` counts **UTF-16 units**, not display characters or Unicode code points. A supplementary emoji, such as 🚀 (U+1F680), requires two UTF-16 code units. Thus the string `"A🚀"` has `length() == 3` but `codePoints().count() == 2`. When handling Unicode, do not treat every `charAt(i)` as a complete Unicode character.

## 3. Four common implementations

| Implementation | Can content change? | Default `equals` equality of that type | Notes when passing into an API |
| --- | --- | --- | --- |
| `String` | No; String values are immutable | By **content**, between two `String` objects | Suitable for storage and as immutable keys |
| `StringBuilder` | Yes: `append`, `setCharAt`, `delete`… | By **object identity** because it does not override `Object.equals` | Two builders with the same characters still have `equals == false` |
| `StringBuffer` | Yes; individual operations are synchronized | By **object identity**, does not compare content | Synchronizing individual calls does not make it immutable or guarantee a snapshot across multiple calls |
| `CharBuffer` | Can mutate content or position/limit state; can also be a read-only buffer | By content of **remaining characters** between `position` and `limit`, when the argument is also a `CharBuffer` | `equals`/`hashCode` depend on buffer state and can change |

A read-only `CharBuffer` can still change its own **position** (unless the caller refrains from doing so); immutability of backing memory content and object immutability are not the same concept. Changing the position can shorten the "remaining" sequence, causing `toString()`, `equals`, and `hashCode` to change even though the characters in the backing storage did not change.

In particular, `StringBuilder` and `StringBuffer` do not implement a content-comparing `equals` rule like `String`. Concluding that "because they all implement CharSequence, they can be compared by content with equals" is wrong.

## 4. Example: same content but different equals

This is an illustrative snippet placed inside a method:

~~~java
String a = "cat";
StringBuilder b = new StringBuilder("cat");
StringBuffer c = new StringBuffer("cat");

System.out.println(a.equals(b));                   // false
System.out.println(a.contentEquals(b));            // true
System.out.println(b.equals(new StringBuilder("cat"))); // false
System.out.println(c.equals(new StringBuffer("cat")));  // false
~~~

Explanation:

1. `String.equals(Object)` returns true only when the other object is also a `String` with the same characters. `StringBuilder` is not considered the same type.
2. `String.contentEquals(CharSequence)` intentionally checks **the characters currently in the CharSequence** against the String. It is suitable when one side has type `String` and the actual goal is text comparison.
3. `StringBuilder.equals` and `StringBuffer.equals` inherit **reference** equality semantics from `Object`; two distinct instances do not become equal because their characters match.
4. `Objects.equals(a, b)` only handles null safely and then calls `a.equals(b)`; it **does not turn** equals into cross-implementation content comparison.

`CharBuffer.wrap("cat").equals(CharBuffer.wrap("cat"))` returns `true` because the two buffers have the same remaining character sequence. But `"cat".equals(CharBuffer.wrap("cat"))` is still false. Therefore, you cannot write a rule that "CharSequence.equals is always content-based" applying to every implementation.

### When text-based comparison is needed

If one side is already a `String`, you can use `expected.contentEquals(actual)` when `actual` is a non-null `CharSequence`. If consistent comparison is needed at the API boundary, create an explicit snapshot:

~~~java
static boolean sameText(CharSequence first, CharSequence second) {
    java.util.Objects.requireNonNull(first, "first");
    java.util.Objects.requireNonNull(second, "second");
    return first.toString().equals(second.toString());
}
~~~

This is an **illustrative method**, not a standalone program. It defines a comparison rule using the `String` content obtained at call time; it does not impose each implementation's `equals` style. The key assumption is that the source content is stable while the two snapshots are taken. If the objects are modified concurrently, synchronization must follow the application contract.

## 5. Mutability: holding a reference does not mean holding the content

Consider the example:

~~~java
StringBuilder builder = new StringBuilder("cat");
CharSequence savedReference = builder;
String savedSnapshot = builder.toString();

builder.append("s");

System.out.println(savedReference); // cats
System.out.println(savedSnapshot);  // cat
~~~

`savedReference` still points to **the same mutable builder**, so reading it after the modification yields `"cats"`. `savedSnapshot` is a `String` taken from the `"cat"` value before the modification, so it does not change. Immutability comes from **the held object**, not from the variable type used to reference it.

This affects APIs like:

~~~java
final class NoteStore {
    private CharSequence title;

    void setTitle(CharSequence title) {
        this.title = title; // Holds a reference to a mutable source
    }

    CharSequence getTitle() {
        return title;
    }
}
~~~

The `NoteStore` snippet is an **anti-pattern**: the caller can pass a `StringBuilder`, then edit the builder after storing it. Then `getTitle()` returns different content from when `setTitle` was called without `NoteStore` modifying anything.

A safer design if the contract intends to keep "the value at the time it was passed":

~~~java
final class StableNoteStore {
    private String title;

    void setTitle(CharSequence value) {
        title = java.util.Objects.requireNonNull(value, "value").toString();
    }

    String getTitle() {
        return title;
    }
}
~~~

Using `String` for stored state makes it clear that this is an **immutable value**, not a sequence of characters that can change. Note: `toString()` captures the current content into a `String`; if the implementation is mutated concurrently during the snapshot, a locking mechanism or appropriate ownership agreement is needed. There is no universal `toString()` call that guarantees every implementation is thread-safe.

## 6. subSequence can be a live view

Do not assume that calling `subSequence` always creates an immutable copy. `CharBuffer` is a practical illustration:

~~~java
char[] data = {'c', 'a', 't'};
java.nio.CharBuffer buffer = java.nio.CharBuffer.wrap(data);
CharSequence tail = buffer.subSequence(1, 3);
String stableTail = tail.toString();

data[1] = 'o';

System.out.println(tail);       // ot
System.out.println(stableTail); // at
~~~

`tail` is a view backed by the `data` character array. Changing the underlying array from `a` to `o` is reflected in the view, while `stableTail` retains the old content.

**Design conclusion:** returning `CharSequence` from an API can be reasonable when intentionally providing a view, but users need to know **who owns the buffer**, **how long the view lives**, **who is allowed to mutate it**, and **when a snapshot is required**. If the requirement is to return a long-term stable value, returning a `String` is usually simpler.

## 7. Pitfalls when using CharSequence as a collection key

When serving as a key in a `HashMap`/`HashSet`, an object must satisfy stable `equals` and `hashCode` rules while residing in the collection.

- An immutable `String` key has clear content-based `equals`/`hashCode`, making it suitable as a key.
- A `StringBuilder` key compares by object identity; even with the same text, two separate builders are **two distinct keys**. Mutating a builder does not turn `Object.hashCode` into content hashing.
- A `CharBuffer` key has `equals`/`hashCode` based on its remaining characters. Changing `position`, `limit`, or the underlying content can change its equality semantics and hash value while the object is a key. Lookup based on the old bucket may then behave unexpectedly.

Illustrative example:

~~~java
java.util.Set<CharSequence> keys = new java.util.HashSet<>();
keys.add("cat");
keys.add(new StringBuilder("cat"));
keys.add(java.nio.CharBuffer.wrap("cat"));

System.out.println(keys.size()); // 3
~~~

The three objects above have the same displayed text but carry different `equals` behaviors, so all three can coexist separately. **Do not use `CharSequence` as a key when the business key definition is actually "same text content" without normalizing or snapshotting.** Take `String normalizedKey = incoming.toString()` before inserting into `Map<String, ...>`/`Set<String>` if you want equality according to `String.equals`.

Do not write tests asserting "after mutating CharBuffer, HashMap.get always returns null": the outcome can depend on hash buckets and specific state. Instead, verify directly that a buffer's `equals`/`hashCode` can change with `position` and enforce the rule **never mutate key fields that affect hashing**.

## 8. Complete Java 17+ program

The file **CharSequenceApiDemo.java** below directly checks the differences just discussed: `String.equals`, `contentEquals`, identity equality, `CharBuffer` equality, mutable builder, mutable view, snapshot, Unicode, and null.

~~~java
import java.nio.CharBuffer;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class CharSequenceApiDemo {
    private static int passed;

    private static void check(String name, boolean ok) {
        if (!ok) {
            throw new AssertionError("FAILED: " + name);
        }
        passed++;
    }

    static String snapshot(CharSequence text) {
        return Objects.requireNonNull(text, "text").toString();
    }

    public static void main(String[] args) {
        String text = "cat";
        StringBuilder builder = new StringBuilder("cat");
        StringBuffer buffer = new StringBuffer("cat");
        CharBuffer charBuffer1 = CharBuffer.wrap("cat");
        CharBuffer charBuffer2 = CharBuffer.wrap("cat");

        check("String.equals checks type", !text.equals(builder));
        check("String.contentEquals", text.contentEquals(builder));
        check("Objects.equals not content comparison",
                !Objects.equals(text, builder));
        check("StringBuilder identity equality",
                !builder.equals(new StringBuilder("cat")));
        check("StringBuffer identity equality",
                !buffer.equals(new StringBuffer("cat")));
        check("CharBuffer content equality",
                charBuffer1.equals(charBuffer2));
        check("CharBuffer versus String",
                !charBuffer1.equals(text) && !text.equals(charBuffer1));
        check("equal CharBuffers have same hash",
                charBuffer1.hashCode() == charBuffer2.hashCode());

        Set<CharSequence> mixed = new HashSet<>();
        mixed.add(text);
        mixed.add(builder);
        mixed.add(charBuffer1);
        check("mixed set has three keys", mixed.size() == 3);

        String fixed = snapshot(builder);
        builder.append("s");
        check("snapshot is immutable", fixed.equals("cat"));
        check("builder changes", builder.toString().equals("cats"));

        charBuffer1.position(1);
        check("CharBuffer remaining content changed",
                charBuffer1.toString().equals("at"));
        check("CharBuffer equality changed",
                !charBuffer1.equals(charBuffer2));
        check("CharBuffer hash changed",
                charBuffer1.hashCode() != charBuffer2.hashCode());

        char[] array = {'c', 'a', 't'};
        CharBuffer view = CharBuffer.wrap(array);
        CharSequence sub = view.subSequence(1, 3);
        check("initial subSequence", sub.toString().equals("at"));
        String subCopy = snapshot(sub);
        array[1] = 'o';
        check("backed view reflects mutation", sub.toString().equals("ot"));
        check("snapshot of view is stable", subCopy.equals("at"));

        CharSequence unicode = new StringBuilder("A\uD83D\uDE80");
        check("UTF-16 units differ from code points",
                unicode.length() == 3 && unicode.codePoints().count() == 2);
        check("null rejection", rejectsNull());

        System.out.println("String.equals(StringBuilder)="
                + text.equals(new StringBuilder("cat")));
        System.out.println("String.contentEquals(StringBuilder)="
                + text.contentEquals(new StringBuilder("cat")));
        System.out.println("HashSet.size=" + mixed.size());
        System.out.println("BuilderSnapshot=" + fixed);
        System.out.println("BuilderNow=" + builder);
        System.out.println("CharBufferAfterPosition=" + charBuffer1);
        System.out.println("ViewAfterArrayChange=" + sub);
        System.out.println("ViewSnapshot=" + subCopy);
        System.out.println("PASS: " + passed + " checks");
    }

    static boolean rejectsNull() {
        try {
            snapshot(null);
            return false;
        } catch (NullPointerException expected) {
            return true;
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CharSequenceApiDemo.java
java CharSequenceApiDemo
~~~

Exact stdout if all 19 checks succeed:

~~~text
String.equals(StringBuilder)=false
String.contentEquals(StringBuilder)=true
HashSet.size=3
BuilderSnapshot=cat
BuilderNow=cats
CharBufferAfterPosition=at
ViewAfterArrayChange=ot
ViewSnapshot=at
PASS: 19 checks
~~~

The `check` function throws `AssertionError` if any case fails, so there is no false `PASS` line when results are wrong. Java's `assert` is not used because `assert` is disabled by default unless `-ea` is enabled.

Notable point in the example: `CharBuffer.equals` and `hashCode` reflect the remaining text from `position` to `limit`; after `charBuffer1.position(1)`, its current sequence changes from `"cat"` to `"at"` without necessarily modifying the original character array. Conversely, the `String` returned from `snapshot` still holds the value from before the object was modified.

## 9. How to choose parameter and return types

| API Purpose | Type Suggestion | How to Handle |
| --- | --- | --- |
| Read input immediately within the call, without retaining it | `CharSequence` | Can accept multiple data sources; clearly document that the source must not be modified during processing |
| Store text, cache, or pass to asynchronous processing | Accept `CharSequence` if flexibility is needed; **store `String`** | Take a snapshot once at the ownership boundary |
| Use as Map/Set keys by text content | `String` | Normalize if needed, then store/compare using `String.equals` and `hashCode` |
| Return a stable text value | `String` | The receiver knows this is an immutable value |
| Return a view that can reflect the source | `CharSequence` / `CharBuffer` | Document backing storage, lifecycle, position/limit, and update rules |
| Sort by characters | Explicitly defined `Comparator` | Do not automatically equate `compare == 0` with `equals` for all CharSequences |

If the API wants to **keep the external mutable data type as-is**, it must clearly specify mutation rules, thread-safety, and data lifetime. If the API needs an **independent snapshot value**, flexible input and immutable internals are an easier choice to prove correct.

### Null and input contracts

A `CharSequence` parameter can still be `null`. Decide whether null is **rejected**, **treated as an empty string**, or **handled by a specific policy**. Example of explicit rejection:

~~~java
static String snapshot(CharSequence input) {
    return java.util.Objects.requireNonNull(input, "input").toString();
}
~~~

This is an illustrative method snippet whose runnable version appears in the program above. Avoid casually calling `String.valueOf((Object) input)` when null signifies an error: it converts null into the text `"null"`, which can mask invalid data.

### Concurrency and ownership

`StringBuilder` is not thread-safe. `StringBuffer` synchronizes many individual methods, but a procedure consisting of `length()`, then looping `charAt()`, or combining multiple calls is not guaranteed to be an atomic snapshot if another thread modifies the data concurrently. `CharBuffer` also has mutable state. If multiple threads can modify the input, **cooperative locking**, **ownership transfer**, or **a stable copy created before sharing** is needed.

Even when an API declares `CharSequence` as a `final` parameter, the `final` keyword only prevents **reassigning the reference variable** inside the method; it does not make the object immutable.

## 10. Test matrix for APIs accepting CharSequence

| Case | Required Test |
| --- | --- |
| Two `String` instances with the same content | Same `equals` and `hashCode` |
| `String` and `StringBuilder` with the same content | `String.equals` returns false; explicit content comparison returns true |
| Two `StringBuilder` instances with the same content | Must not assume they are `equals` |
| Two `StringBuffer` instances with the same content | Must not assume they are `equals` |
| Two `CharBuffer` instances with the same remaining content | Compared by remaining content |
| `CharBuffer` changes `position` | Logical content, `equals`, and `hashCode` may change |
| `CharBuffer` view of `char[]` | Modifying the backing array can change what the view observes |
| `StringBuilder` modified after passing | The reference changes accordingly, while a `String` snapshot remains unchanged |
| Object used as a collection key | Matches intended equality rules; do not mutate fields participating in `hashCode` |
| Content with supplementary emoji | `length()` counts UTF-16 code units; `codePoints()` counts code points |
| `null` input | Clear handling policy with tests |
| Data modified from multiple threads | Snapshot or synchronize per contract; do not assume every CharSequence is thread-safe |

## 11. Common mistakes and how to avoid them

1. **Writing `a.equals(b)` to compare two arbitrary `CharSequence` values:** comparison depends on the implementation. If the requirement is "same text", normalize to a String snapshot or use an appropriate content-comparison API.
2. **Storing `CharSequence` long-term and treating it as immutable:** external code can still modify the builder or backing array. Store `String` when stable state is needed.
3. **Using CharBuffer as a hash key and then changing position:** the hash value can change, violating hash collection invariants.
4. **Assuming `subSequence` always copies:** some implementations return a view sharing the source. When a guaranteed snapshot is needed, take a `String`.
5. **Believing `StringBuffer` makes every sequence of operations atomic:** per-method synchronization does not span a multi-step algorithm.
6. **Using `final CharSequence` to "prevent mutation":** `final` does not freeze the object.
7. **Using `length()` to count displayed characters:** UTF-16 code units differ from code points; code points in turn differ from grapheme clusters.
8. **Calling `Objects.equals` thinking it compares content:** it still calls the concrete object's `equals`; it only adds null handling.
9. **Calling `toString()` multiple times within the same calculation on a mutable source:** you may get different snapshots. If you need one consistent snapshot, take it once at an appropriate boundary and process that String.

## 12. Self-check questions

**Question 1.** A method accepts `CharSequence input` and assigns `this.value = input`. The caller passes `StringBuilder("abc")`, then appends `"d"`. What content is read from `value`?

Answer: following the reference to the same builder, the current content will be `"abcd"`. To store `"abc"` as of the time of the call, a `String` snapshot must be taken.

**Question 2.** Why is `new StringBuilder("x").equals(new StringBuilder("x"))` false?

Answer: `StringBuilder` does not override `Object.equals` by content, so two objects with different identities are not equal.

**Question 3.** Why can two `CharBuffer.wrap("x")` instances be equal, while `"x".equals(CharBuffer.wrap("x"))` is false?

Answer: `CharBuffer.equals` compares remaining content with another `CharBuffer`. `String.equals` only considers objects of type `String` with the same content to be equal.

**Question 4.** If an API wants to cache a caller-supplied string for several hours, should it store `CharSequence` or `String`?

Answer: if stable content as of the time received is needed, store a `String` snapshot (along with a null policy and synchronization if the source can be modified concurrently).

**Question 5.** A `CharBuffer` is already inside a `HashSet`. Is it safe to advance its position and continue using that buffer as a key?

Answer: it should not be done; `CharBuffer`'s `equals`/`hashCode` depend on the remaining data, so changing position can make key lookup rules unstable.

## 13. Takeaways

**`CharSequence` describes the ability to read a sequence of UTF-16 code units; it does not guarantee immutability or consistent content-based equals across implementations.** Use `CharSequence` for input flexibility, but clearly define ownership, lifetime, and synchronization mechanisms. When you need a **stable text value**, especially for caching or collection keys, create a `String` snapshot and explicitly define content-based comparison.