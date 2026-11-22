# Relationship Between equals, hashCode, and Hash Collisions for Strings in Java

When comparing `String` objects in Java, `equals()` answers **"do these two strings have the same content?"**; `hashCode()` computes an **`int` hash value** from the content to support data structures like `HashMap` and `HashSet`. The two capabilities are tightly linked by a critical contract:

> If two `String` objects are equal according to `equals()`, they **must** have the same `hashCode()`. The converse is **not true**: two **different** strings can easily share the same hash value (*hash collision*).

Understanding this contract helps avoid confusing **identity**, **content comparison**, and **hashing for lookup**; it also explains why hash-based collections can still distinguish two different strings that have the same hash value.

## 1. What Does equals() Compare?

`String.equals(Object other)` returns `true` when `other` is a `String` object with the same **sequence of UTF-16 code units** (same length and same `char` value at every position). The comparison is case-sensitive. Example:

~~~java
String a = "Java";
String b = new String("Java");
String c = "java";

System.out.println(a.equals(b));  // true
System.out.println(a.equals(c));  // false
System.out.println(a == b);       // false
~~~

This is an **illustrative code snippet** placed inside a Java method. `a.equals(b)` is `true` because the contents match; `a == b` is `false` because `new String("Java")` creates a separate object. The `==` operator on two object references asks whether they point to the **same object**; it is not a string content equality check.

Notes:

- `equals()` returns `false` when the argument is `null` or not a matching `String`.
- Calling `nullReference.equals(...)` throws `NullPointerException`. When values may be `null`, use `java.util.Objects.equals(a, b)` for null-safe comparison.
- `String` is immutable: once created, its content does not change; thus `equals()` and `hashCode()` of a `String` object remain stable throughout its lifetime.
- `equalsIgnoreCase()` is a **different comparison method**: it does not make two strings with different casing equal under `equals()`.

### "Same Content" in Java Does Not Always Mean "Looks Identical"

`equals()` compares UTF-16 sequences and does not auto-normalize Unicode. For instance, precomposed `é` (`U+00E9`) and `e` plus combining acute accent (`U+0065 U+0301`) may look identical yet have different code-unit sequences. Similarly, `equals()` does not strip whitespace or convert uppercase to lowercase. If business logic wants to treat those representations as equivalent, you must **define explicit normalization/comparison rules** before using them as keys.

## 2. How Is String's hashCode() Computed?

According to the Java API contract, `String.hashCode()` is computed from its `char` values using a base-**31** polynomial formula:

\[
h = s[0]\cdot 31^{n-1} + s[1]\cdot 31^{n-2} + \ldots + s[n-1]
\]

Here `n = s.length()` and `s[i]` is the **UTF-16 code unit** at index `i`, not necessarily a full Unicode code point. Arithmetic uses 32-bit signed `int`, so multiplications and additions can **overflow under Java rules**, corresponding to a result modulo \(2^{32}\); the hash value can be negative. The empty string has `hashCode() == 0`.

You can picture the equivalent algorithm below (illustrative logic, not required internal JVM source code):

~~~java
static int manualStringHash(String s) {
    int hash = 0;
    for (int i = 0; i < s.length(); i++) {
        hash = 31 * hash + s.charAt(i);
    }
    return hash;
}
~~~

This is an **illustrative method** that must be placed inside a Java class. In `int` arithmetic, overflow wraps according to Java rules without throwing an exception. For normal `String`s, this function yields the same result as `s.hashCode()`.

**Meaning:** the same code-unit sequence always yields the same hash value, regardless of whether two strings were created via literals, `new String(...)`, concatenation, or file I/O. Yet no information inside the `int` value uniquely identifies the original string.

## 3. The Contract Between equals() and hashCode()

| Relationship Between Two Strings `a`, `b` | Required Consequence | What Cannot Be Concluded |
| --- | --- | --- |
| `a.equals(b) == true` | `a.hashCode() == b.hashCode()` | Does not imply `a == b` |
| `a.hashCode() != b.hashCode()` | `a.equals(b) == false` | Says nothing about lexicographical order between `a` and `b` |
| `a.hashCode() == b.hashCode()` | Only known that both hashes match | **Cannot conclude** `a.equals(b) == true` |
| `a.equals(b) == false` | Content differs | The two hashes **may collide or differ** |

One way to remember it:

~~~text
a.equals(b) == true
        |
        v
a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()
        |
        +---- possibly a.equals(b) == true
        |
        +---- or possibly a.equals(b) == false
              (hash collision)
~~~

This contract applies to objects whose `equals()` and `hashCode()` conform to `Object`'s specification. `String` already implements it properly. When building your own class to serve as a `HashMap` key, overriding `equals()` generally requires **overriding a compatible `hashCode()`** so equal objects produce identical hash values.

Having the same hash also does not make `equals()` return `true`, because `equals()` does not define equality solely through hash values. The hash value is merely a **helper step for lookup/bucketing**.

## 4. Famous Collision Example: "Aa" and "BB"

The following two strings with **different content** have the exact same hash value:

~~~java
String first = "Aa";
String second = "BB";

System.out.println(first.hashCode());      // 2112
System.out.println(second.hashCode());     // 2112
System.out.println(first.equals(second));  // false
~~~

Calculating by `String`'s formula using ASCII UTF-16 values:

- `"Aa"`: `'A' = 65`, `'a' = 97`, so `65 * 31 + 97 = 2112`.
- `"BB"`: `'B' = 66`, so `66 * 31 + 66 = 2112`.

The hashes match because both calculations produce the same integer; the characters in the strings still differ. **This is a hash collision**, not a Java bug.

Collisions are **impossible to eliminate completely** in a hash function returning `int`: infinitely many `String`s can be constructed, whereas `hashCode()` has only \(2^{32}\) possible return values. By the pigeonhole principle, many distinct strings must share a hash value.

Noticeably, even without integer overflow, short strings like `"Aa"` and `"BB"` already collide. Therefore **never use hashes as sole proof of equality**.

## 5. Java 17+ Program Verifying equals, HashSet, and HashMap

Save the following program to **`StringHashCollisionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringHashCollisionDemo {
    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";
        String sameContent = new String("Aa");

        System.out.println("first hash = " + first.hashCode());
        System.out.println("second hash = " + second.hashCode());
        System.out.println("hash collision = "
                + (first.hashCode() == second.hashCode()));
        System.out.println("first equals second = " + first.equals(second));
        System.out.println("first equals sameContent = "
                + first.equals(sameContent));
        System.out.println("first == sameContent = "
                + (first == sameContent));

        Set<String> set = new HashSet<>();
        set.add(first);
        set.add(second);
        set.add(sameContent);
        System.out.println("set size = " + set.size());

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 1);
        map.put(second, 2);
        map.put(sameContent, 3);

        System.out.println("map size = " + map.size());
        System.out.println("map Aa = " + map.get(new String("Aa")));
        System.out.println("map BB = " + map.get("BB"));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 StringHashCollisionDemo.java
java StringHashCollisionDemo
~~~

**Exact stdout:**

~~~text
first hash = 2112
second hash = 2112
hash collision = true
first equals second = false
first equals sameContent = true
first == sameContent = false
set size = 2
map size = 2
map Aa = 3
map BB = 2
~~~

Explanation:

1. `first` and `second` share the hash `2112` yet differ in content, so `equals()` returns `false`.
2. `sameContent` is a different `String` object from `first`, yet has content `"Aa"`, so `first.equals(sameContent)` returns `true` and they share the same hash.
3. `HashSet` stores **two** elements: `"Aa"` and `"BB"`. Colliding hash values **do not cause one string to be dropped**; the third element `sameContent` is not added because it is **equal via `equals()`** to the existing `"Aa"`.
4. `HashMap` keeps **two** keys `"Aa"` and `"BB"`. Calling `put(sameContent, 3)` updates the value associated with the `"Aa"` key from `1` to `3` instead of creating a third key.
5. `map.get(new String("Aa"))` retrieves `3` accurately even though the lookup key is a newly allocated object.

Do not rely on **iteration order** of `HashMap`/`HashSet` in tests: these collections do not guarantee list-like ordering. The example above prints only sizes and key-based lookups, avoiding dependence on iteration order.

## 6. Why Do HashMap and HashSet Still Work When Hashes Collide?

The general idea of hash-based structures in Java is combining **hash codes to narrow down the search** with **equality checks to confirm the exact key**:

~~~text
key (String)
     |
     v
hashCode() --> pick slot/search region in table
                    |
                    v
            candidate entries
                    |
                    v
             equality check
            (equals/identity)
                    |
            +-------+--------+
            |                |
          equal          not equal
            |                |
     same logical key   different key, even if
     (update/lookup)     hashes may collide
~~~

This diagram is a **conceptual model**. The actual `HashMap` implementation includes hash-bit spreading, bucket selection, bucket organization, and optimizations across JDK versions. The core public semantics are that `String` keys are distinguished by `equals()`, never exclusively by `hashCode()`.

- **Hash collision + `equals()` returns `true`:** same logical key; typically overwrites/updates the value in `HashMap`; `HashSet.add()` does not increase size.
- **Hash collision + `equals()` returns `false`:** two distinct logical keys; both can coexist in `HashMap` and `HashSet`.
- **Different hashes:** two `String`s cannot be equal under `equals()`, as that would violate the forward direction of the contract.

Having many colliding keys can increase comparison counts and affect **performance**, yet it must never break lookup correctness. Implementation-level optimizations do not turn hashes into unique identifiers.

### Distinguishing Three Easily Confused Operations

| Operation | Question Answered | Can It Replace the Others? |
| --- | --- | --- |
| `a == b` | Same object reference? | Cannot replace `equals()` when content is needed |
| `a.equals(b)` | Equal `String` value? | Right for verbatim content comparison |
| `a.hashCode() == b.hashCode()` | Same 32-bit hash code? | **Cannot** replace `equals()` due to collisions |

If your goal is genuinely **keying by string content**, pass the `String` itself as the key of `Map<String, ...>` or element of `Set<String>`. Never convert a string into an `int` via `hashCode()` and use that `int` as a "unique ID" to store or overwrite data.

## 7. Implementing an Equivalent Hash Function to Verify

To see why hash values depend on **UTF-16 content**, you can implement the calculation yourself:

~~~java
public class ManualStringHashDemo {
    static int compute(String s) {
        int result = 0;
        for (int index = 0; index < s.length(); index++) {
            result = 31 * result + s.charAt(index);
        }
        return result;
    }

    public static void main(String[] args) {
        String[] examples = {"", "Aa", "BB", "Java", "😀"};
        for (String text : examples) {
            System.out.println(compute(text) == text.hashCode());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ManualStringHashDemo.java
java ManualStringHashDemo
~~~

Output:

~~~text
true
true
true
true
true
~~~

This program shows that `String.hashCode()` is determined by the published formula, even for strings containing an emoji made of a surrogate pair. **Internal memory layout** or JVM object optimizations do not alter the hash value promised by the API.

Because the hash uses UTF-16 units in its formula, it is **not** a UTF-8 encoding, file byte checksum, or Unicode code-point counter. A hash reveals neither how many displayed characters a string has nor how to recover the original text.

## 8. Different Comparison Rules Require Consistent Key Rules

### Uppercase and Lowercase

`equalsIgnoreCase()` does not participate in `String.hashCode()`'s contract. Example:

~~~java
System.out.println("A".equalsIgnoreCase("a")); // true
System.out.println("A".equals("a"));           // false
System.out.println("A".hashCode());            // 65
System.out.println("a".hashCode());            // 97
~~~

This is an **illustrative code snippet** inside a method. Two strings can match under **case-insensitive rules**, yet their hashes differ because `String.hashCode()` is computed from **original content**. This aligns completely with `String`'s `equals()` contract because `"A".equals("a")` is `false`.

To build a case-insensitive lookup table, explicitly define business rules: for example, normalize keys before storing and looking up using the same rule, or use a suitable structure/comparator such as `TreeMap<>(String.CASE_INSENSITIVE_ORDER)` if the comparator's matching behavior fits requirements. For multilingual Unicode, case conversion, locale, and case-insensitive matching require careful attention; calling `toLowerCase()` arbitrarily does not automatically guarantee all desired case-folding or normalization behavior.

### Unicode Normalization

The letter `é` can be represented by the precomposed code point `U+00E9` or by `e` + combining acute accent `U+0301`:

~~~java
import java.text.Normalizer;

// Illustrative code snippet inside a Java method:
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.hashCode());         // 233
System.out.println(decomposed.hashCode());       // 3900

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

Because the code-unit sequences differ, `equals()` and `hashCode()` on **unnormalized** strings can also differ. Here, NFC turns the decomposed string into precomposed content, so `equals()` returns `true` and by contract their hashes also match.

If canonically equivalent Unicode strings should act as the same key, you must **normalize consistently on both insertion and lookup**, and document what counts as "equivalent" in the application. You cannot use `hashCode()` alone to perform normalization or semantic comparison.

## 9. Common Mistakes

| Mistake | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| `a.hashCode() == b.hashCode()` guarantees `a.equals(b)` | Hash collisions exist; `"Aa"` and `"BB"` are a counterexample | When checking identical content, use `equals()` |
| Two strings with the same hash mean `HashSet` keeps only one | `HashSet` distinguishes elements via equality logic | Both `"Aa"` and `"BB"` coexist |
| `==` instead of `equals()` | `==` on references checks object identity | Use `equals()` for strings |
| Using `hashCode()` as a unique string ID | It is only a 32-bit integer with collisions | Keep the original string key or use a dedicated managed ID |
| Using hash to detect modified strings or tampered data | `String.hashCode()` is non-cryptographic; collisions are easy to craft | Choose cryptographic tools suitable for security |
| Using `equalsIgnoreCase()` and expecting hashes to ignore case too | `hashCode()` still uses exact `String` content | Design consistent key normalization/comparison |
| Visually identical characters must have the same hash | Unicode code-unit sequences may differ | Define Unicode normalization rules beforehand |
| `String.hashCode()` depends on object address | `String` hash is computed from content | Two `String` objects with equal content always hash identically |
| Comparing hashes alone to save time | Can report false equality; hashing is not free either | Use standard collections and comparison APIs, letting the structure handle collisions |

**Security note:** `String.hashCode()` is a **non-cryptographic** hash; it is predictable and easy to collide deliberately. Never use it for signatures, password verification, tamper-resistant integrity checks, or proving uniqueness. Security tasks require dedicated algorithms and designs.

## 10. Checklist for Using String as a Key

1. Define what **"two keys are considered equal"** means: verbatim, case-insensitive, Unicode-normalized, or another business rule?
2. If **verbatim**, use `String` directly as the key in `HashMap<String, V>` / `HashSet<String>`; `String`'s `equals()` and `hashCode()` already align.
3. If **normalization** is required, apply the exact same transformation to every key on storage and retrieval; mind locale and Unicode data.
4. Never compare solely by hash and never turn `hashCode()` into a unique identifier.
5. Test both **different-content colliding-hash** pairs like `"Aa"` and `"BB"`, and **equal-content different-object** pairs like literal `"Aa"` and `new String("Aa")`.
6. When accepting nullable values, apply appropriate null checks; never call `s.equals()` or `s.hashCode()` directly on a `null` reference.
7. Evaluate performance if many keys come from untrusted sources that could intentionally trigger collisions; correctness and performance characteristics are separate concerns.

## 11. Self-Check

**Question 1.** If `a.equals(b)` is `true`, can `a.hashCode() != b.hashCode()` ever happen for two valid Java `String`s?

**Answer:** no. That is the mandatory forward direction of the `equals()` / `hashCode()` contract.

**Question 2.** If two `String`s have the same `hashCode()`, is that enough to conclude they are equal?

**Answer:** no. `"Aa"` and `"BB"` share hash `2112`, yet `equals()` returns `false`.

**Question 3.** Inserting `"Aa"` and `"BB"` into a `HashSet<String>` yields how many elements?

**Answer:** two. They have colliding hashes but differ under `equals()`.

**Question 4.** Given `Map<String, Integer> m`, after `m.put("Aa", 1); m.put(new String("Aa"), 2);`, does the size grow to two?

**Answer:** no. Both keys are equal under `equals()`, so the logical key `"Aa"` has its value updated to `2`; size remains one.

**Question 5.** Why does `"A".equalsIgnoreCase("a")` equal `true` while their differing hashes `65` and `97` do not violate the contract?

**Answer:** the contract is based on `equals()`, and `"A".equals("a")` is `false`. `equalsIgnoreCase()` is a separate comparison rule.

**Question 6.** Why should `String.hashCode()` not be stored as a unique ID for usernames?

**Answer:** many different strings can share the same hash; using a hash as a unique ID could mistakenly equate different users. Store and compare by the proper key or a dedicated managed ID system.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): contracts of `equals()`, `hashCode()`, `equalsIgnoreCase()`, and the string hashing formula.
- [Java SE 17 — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): general contract between `equals()` and `hashCode()`.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hash table behavior with keys and values.
- [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): set that rejects duplicate elements under equality.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): normalizing Unicode representations when business requirements call for it.
