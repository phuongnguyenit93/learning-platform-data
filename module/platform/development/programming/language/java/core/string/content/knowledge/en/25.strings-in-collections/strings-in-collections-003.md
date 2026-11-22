# Comparing `String` by Content Instead of Relying on `intern()` in Java Collections

## 1. The Practical Problem

Suppose an application receives the key name `"java"` from two sources: one written directly in source code, and another read from external data or constructed as a new string. Both values have identical content, but they are not necessarily the same **`String` object**.

~~~java
String a = "java";
String b = new String("java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Both represent the four letters `j`, `a`, `v`, `a`. The expression `a == b` evaluates to `false` because the two variables reference **two different objects**. The expression `a.equals(b)` evaluates to `true` because `String.equals` compares **string content**.

In `Set<String>`, `Map<String, ...>`, or deduplication operations, the business rule is usually: **identical content is treated as the same key or the same element**. Therefore, you should rely on `equals()` and `hashCode()`, rather than trying to make every string point to a single `intern()`ed object.

A program might "work by accident" with `==` when all values are string literals, and then fail when data comes from files, networks, databases, or runtime string concatenation.

## 2. Distinguishing `==`, `equals()`, and `intern()`

| Expression / API | What it checks or does | Appropriate when |
| --- | --- | --- |
| `a == b` | Whether two references point to the same object | Intentionally checking **object identity** |
| `a.equals(b)` | Whether two `String`s have the same sequence of UTF-16 code units | Checking exact, case-sensitive **content** |
| `Objects.equals(a, b)` | Content comparison that is safe when one or both variables may be `null` | Comparing nullable values |
| `a.equalsIgnoreCase(b)` | Case-insensitive comparison using Java's rules | When business logic explicitly defines this comparison as appropriate |
| `a.intern()` | Returns a canonical reference from the string pool for the content of `a` | Intentional optimization or specialized technical cases |
| `a.hashCode()` | Produces a stable hash value based on `String` content | Hash-based collections, such as `HashSet` and `HashMap` |
| `a.compareTo(b)` | Lexicographical comparison by UTF-16 code units | Sorting by `String`'s **natural order** |

Key point to remember: `String.intern()` is **not** a check for whether two strings are equal. It returns a canonical representative reference, allowing strings with equal content to share one object once interned. If the goal is **value comparison**, calling `equals()` directly is both clearer in intent and independent of any reference-canonicalization step.

### How does `intern()` work?

The JVM maintains a **string pool** for interned strings. String literals such as `"java"` are interned. When calling `someString.intern()`, the result is the canonical representative object with the same content already in the pool, or an object becomes the representative for that content if none existed beforehand.

~~~java
String literal = "java";
String created = new String("java");

System.out.println(literal == created);          // false
System.out.println(literal == created.intern()); // true
System.out.println(created == created.intern()); // false
~~~

`created.intern()` **returns a reference**; it does not change the content and does not turn the `created` object itself into the string literal. Using `intern()` here only explains the mechanism, not a solution to use for collection comparisons.

The explicitly constructed `new String("java")` case is a clear illustration; for compiler-optimized strings or compile-time constant expressions, do not mechanically assume that every concatenation expression creates a new object.

## 3. Verifying That `intern()` Is Unnecessary for Hash Collections

Two newly created instances containing the same characters are still **one** `HashSet` element and **one** `HashMap` key. There is no need to pre-canonicalize references with `intern`:

~~~java
String a = new String("id-42");
String b = new String("id-42");

Set<String> set = new HashSet<>();
set.add(a);
set.add(b);
System.out.println(set.size()); // 1

Map<String, Integer> map = new HashMap<>();
map.put(a, 10);
map.put(b, 20);
System.out.println(map.size()); // 1
System.out.println(map.get("id-42")); // 20
~~~

`intern` only returns a canonical reference from the string pool; comparing with `==` after `intern` checks the identity of **the interned references**, rather than changing the contract of `HashMap` or `HashSet`. Two different contents remain different; two equal contents are already equal even before interning. If a map using true **identity** is needed, a specialized structure like `IdentityHashMap` must be chosen, which has different semantics from `HashMap` (section 6).

**Hash collisions are a separate issue**: `"Aa".hashCode() == "BB".hashCode()`, yet `"Aa".equals("BB")` is `false`. Never compare two contents by hash alone; details of the contract are covered in the lesson on hash collisions.

## 5. Complete, Runnable Java 17+ Example

Save the program as `StringCollectionEqualityDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class StringCollectionEqualityDemo {
    public static void main(String[] args) {
        String pooled = "java";
        String separate = new String("java");
        String rebuilt = new StringBuilder()
                .append("ja")
                .append("va")
                .toString();

        System.out.println("referenceEquals=" + (pooled == separate));
        System.out.println("valueEquals=" + pooled.equals(separate));
        System.out.println("internEquals=" +
                (pooled == separate.intern()));
        System.out.println("sameHash=" +
                (pooled.hashCode() == separate.hashCode()));

        Set<String> tags = new HashSet<>();
        tags.add(pooled);
        tags.add(separate);
        tags.add(rebuilt);

        System.out.println("hashSetSize=" + tags.size());
        System.out.println("hashSetContains=" +
                tags.contains(new String("java")));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(new String("id-42"), 10);
        scores.put("id-42", 20);

        System.out.println("hashMapSize=" + scores.size());
        System.out.println("hashMapValue=" +
                scores.get(new String("id-42")));

        // Case intentionally using identity instead of content.
        Set<String> identities = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>()
        );
        identities.add(new String("key"));
        identities.add(new String("key"));
        System.out.println("identitySetSize=" + identities.size());

        // Sorted Set can be based on a Comparator.
        Set<String> sorted = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER
        );
        sorted.add("Lan");
        sorted.add("lan");
        System.out.println("treeSetSize=" + sorted.size());
        System.out.println("treeSetContains=" +
                sorted.contains("LAN"));

        System.out.println("equalsIgnoreCase=" +
                "Java".equalsIgnoreCase("JAVA"));
        System.out.println("nullSafe=" +
                Objects.equals(null, null));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("differentFormsEquals=" +
                composed.equals(decomposed));
        System.out.println("normalizedEquals=" +
                composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        System.out.println("collisionHashes=" +
                ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("collisionEquals=" +
                "Aa".equals("BB"));
    }
}
~~~

Compile and run with JDK 17 or later (save the file as UTF-8):

~~~bash
javac -encoding UTF-8 StringCollectionEqualityDemo.java
java StringCollectionEqualityDemo
~~~

`stdout`:

~~~text
referenceEquals=false
valueEquals=true
internEquals=true
sameHash=true
hashSetSize=1
hashSetContains=true
hashMapSize=1
hashMapValue=20
identitySetSize=2
treeSetSize=1
treeSetContains=true
equalsIgnoreCase=true
nullSafe=true
differentFormsEquals=false
normalizedEquals=true
collisionHashes=true
collisionEquals=false
~~~

Key output explanations:

1. The three strings `pooled`, `separate`, and `rebuilt` have the same content `java`; `==` reflects only identity, while `equals` reflects value.
2. `HashSet` stores only one element; `HashMap` stores only one entry with the final value `20`, even though the key objects were created separately.
3. `IdentityHashMap` intentionally uses **`==`** to distinguish keys. Two distinct `new String("key")` objects result in **2** elements in the set backed by the identity map. This is the designed behavior of this specialized collection.
4. `TreeSet` uses `String.CASE_INSENSITIVE_ORDER`, so it treats `"Lan"` and `"lan"` as equivalent under the comparator, even though `"Lan".equals("lan")` is `false`.
5. The two representations of the letter `é` are not `equals` before normalization; `NFC` normalization brings them to the same form.
6. The two strings `Aa` and `BB` produce the same hash code, yet their content is not identical, illustrating why `equals` must still be checked.

## 6. Important Exception: Not Every Collection Uses `String.equals()`

### 6.1. `IdentityHashMap` Uses Object Identity

`IdentityHashMap` is designed to treat two keys as equal only when they reference **the same object**. It is an appropriate structure for certain object-tracking or identity-graph problems, but **inappropriate** when business logic needs to group `String` keys by content.

Example:

~~~java
IdentityHashMap<String, Integer> map = new IdentityHashMap<>();
map.put(new String("user"), 1);
map.put(new String("user"), 2);

System.out.println(map.size()); // 2
~~~

Using `intern()` to force `IdentityHashMap` to behave like `HashMap` is the wrong design direction: you chose a collection with a **different equality relation** and then tried to manipulate references to force the desired result. Choose `HashMap` when content equality is needed.

### 6.2. `TreeSet` and `TreeMap` Use Comparison Order

Sorted collections use `Comparator.compare(a, b) == 0` or `Comparable.compareTo` returning `0` to decide whether two keys are equivalent in the ordered set/map.

With the natural order of `String`, `a.compareTo(b) == 0` is consistent with `a.equals(b)`. However, when passing a case-insensitive comparator:

~~~java
Set<String> names = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
names.add("Admin");
names.add("admin");

System.out.println(names.size()); // 1
System.out.println("Admin".equals("admin")); // false
~~~

Here, `TreeSet` merges the two strings according to the **comparator**, unlike `HashSet`, which distinguishes them using `equals/hashCode`. `String.CASE_INSENSITIVE_ORDER` is inconsistent with `String.equals` for strings differing only in case; therefore, you must consider the `Set` contract when selecting a comparator and not assume both set types share the same duplicate rule.

If a system requires case-insensitive key comparison, define a consistent system-wide strategy (for example, normalizing keys before inserting into a hash collection) and understand the relevant Unicode/locale rules.

## 7. `intern` Is Not a Substitute for Content Normalization

`intern` does **not** change letter case, strip whitespace, or compose Unicode into NFC. Consequently, `"Java"` and `"java"`, or `"\u00E9"` and `"e\u0301"`, remain two distinct values even after each side is `intern`ed. The string pool consolidates references when **content is already equal**; it does not turn different spellings into a single business identifier.

If a product wants multiple spellings to count as one key, define an appropriate canonicalization function and use it for both storage and lookup operations; preserving the original label for display is a separate responsibility. `equalsIgnoreCase` also does not cause `HashMap` to change its key contract. The dedicated lesson on key normalization covers policy selection, Unicode normalization, and handling colliding variants.

## 8. `null` and Choosing Which Side Calls `equals()`

When a value may be `null`, a call like the following is unsafe:

~~~java
String input = null;
// input.equals("ok"); // Throws NullPointerException.
~~~

Safe comparison approaches:

~~~java
import java.util.Objects;

String input = null;
System.out.println("ok".equals(input));       // false
System.out.println(Objects.equals(input, "ok")); // false
System.out.println(Objects.equals(null, null));  // true
~~~

`Objects.equals(a, b)` checks reference equality or `equals` in a null-safe manner: two `null` values are considered equal; one `null` value and one non-`null` value are not equal.

Java's `HashMap` and `HashSet` permit `null` under their own rules, but that does not mean you can invoke `equals()` on a `null` reference. Those are two separate concerns.

## 9. Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| `if (input == "admin")` to check content | Runtime-created data may be misidentified | `"admin".equals(input)` |
| Calling `intern()` before every `HashMap` operation | Adds pool management unnecessary for content equality | Trust `String.equals/hashCode` and pick the right collection |
| Comparing only by `hashCode()` | Hash collisions cause false equality conclusions | Use `equals()` |
| Using `IdentityHashMap` for business string keys | Two objects with identical content can become two keys | Use `HashMap` |
| Assuming `HashSet` and `TreeSet` always handle duplicates identically | `TreeSet` may use a comparator defining a different relation | Choose and verify the comparator explicitly |
| Assuming `equals` auto-trims, ignores case, or normalizes Unicode | Those differences are preserved | Normalize per business rules before storing/looking up |
| Calling `nullable.equals(other)` | May throw `NullPointerException` | `Objects.equals(nullable, other)` or call `equals` on a literal |
| Relying on `==` between two string literals to infer all equal-content strings are the same object | Code only works by chance due to pooling | Use `equals` across all data sources |

### Checklist When Using `String` as a Collection Key

- Is the goal **content equality** or **reference identity**?
- If content equality, does the collection use `equals/hashCode` properly?
- Are rules for case sensitivity, whitespace, and Unicode normalization clearly defined?
- Are inputs from all sources normalized the **same way** before `put`, `add`, `get`, and `contains`?
- If using `TreeMap`/`TreeSet`, does the comparator establish the intended equivalence relation?
- Are nullable strings handled safely?
- Do tests use `new String(...)` or runtime-constructed strings to avoid accidental dependence on the intern pool?

**Conclusion:** For `String` in `HashSet`, `HashMap`, and most value-comparison scenarios, **compare with `equals()`** and rely on the built-in `hashCode()`. `intern()` manages representative objects in the string pool, not the condition for knowing whether two strings share the same content. Use `==` only when **reference identity** is genuinely required, and verify comparator rules when a collection is ordered.
