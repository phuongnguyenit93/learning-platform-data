# `String.equals()` compares content and does not depend on identity

## 1. Distinguishing text value from reference identity

In Java, a `String` variable holds a **reference** to a string object. Therefore, the following two checks answer two different questions:

- **`a == b`** with two references: do the two variables point to the **same object**? This is a *reference identity* check, not a content comparison.
- **`a.equals(b)`**: do the two objects have the same **`String` content**, regardless of whether they reside in two separate objects?

Two `String` instances that are different objects can still have `a == b` be `false` and `a.equals(b)` be `true`. Conversely, if `a == b` and `a` is not `null`, `a.equals(b)` is of course true because it is the same object.

`String` is a `final` class with an *immutable* value. Other code cannot subclass `String` to change how `equals` behaves, and the content of a `String` object does not change after creation. This is why it is suitable as a key in a `HashMap` or an element in a `HashSet`.

**Scope of `equals`:** two objects having the same string content does not mean they represent the same person, the same account, the same record, or the same object in a business model. `equals` only confirms equality according to the class's value definition.

## 2. Contract and mechanism of `String.equals(Object)`

The `String` method overrides the method from `Object`:

```java
public boolean equals(Object anObject)
```

This is an **API signature**, not a standalone runnable program.

Semantically, `String.equals` returns `true` when the argument is a `String` with the **same sequence of UTF-16 code units** in exact order. This is equivalent to having the same `length()` and the same `charAt(i)` value at every valid index. For a `null` argument or an object that is not a `String`, the result is `false`.

The JDK is allowed to optimize how it checks this, such as handling same-reference cases, checking length, comparing data in memory, or using a compact representation; **do not assume a single loop algorithm** from the contract description.

| Expression | Result | Explanation |
| --- | --- | --- |
| `"java".equals("java")` | `true` | Same content |
| `"java".equals("Java")` | `false` | Case-sensitive |
| `"java".equals("java ")` | `false` | Trailing space |
| `"".equals("")` | `true` | Both are empty strings |
| `"java".equals(null)` | `false` | `null` is not a `String` |
| `"java".equals(new StringBuilder("java"))` | `false` | Different object type, even though displayed characters look the same |

`String.equals` does not automatically strip whitespace, ignore case, apply locale-specific language rules, or normalize Unicode. If a different comparison behavior is needed, the application must explicitly define those rules.

## 3. String Pool and why `==` sometimes appears to work

Java string literals use an *interning* mechanism. Literals with the same value such as `"hello"` usually point to the canonical object from the String Pool. Therefore, a `==` check between two identical literals can return `true` and mislead people into thinking `==` is for comparing content.

```java
String a = "hello";
String b = "hello";
String c = new String("hello");

System.out.println(a == b);       // true
System.out.println(a == c);       // false
System.out.println(a.equals(c));  // true
```

This is an **illustrative code snippet**. `a` and `b` receive the same interned string object; `new String("hello")` creates a new object with the same content, so `a == c` is false while `a.equals(c)` is true.

Important scenarios:

1. Two constant literals with the same content are interned according to string literal rules; `"he" + "llo"` is also a constant expression that the compiler can resolve into the literal `"hello"`.
2. Concatenating data from variables at **runtime** can create a different string object. Do not use `==` results with literals to infer rules for data coming from files, the network, or users.
3. `String.intern()` provides a canonical reference, but **there is no need to call it for `equals` to be true**. Interning is a reference-sharing mechanism, not a prerequisite for content equality.
4. `==` still has its place: checking whether references are identical or checking against `null`. When the question is "do two strings have the same text?", choose `equals`.

## 4. Complete runnable Java 17+ example

Create the file `StringEqualityDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringEqualityDemo {
    public static void main(String[] args) {
        String literalA = "java";
        String literalB = "java";
        String separate = new String("java");
        String alias = literalA;

        System.out.println("literal identity: " + (literalA == literalB));
        System.out.println("separate identity: " + (literalA == separate));
        System.out.println("alias identity: " + (literalA == alias));
        System.out.println("content equal: " + literalA.equals(separate));
        System.out.println("case sensitive: " + "Java".equals(separate));
        System.out.println("ignore case: " + "Java".equalsIgnoreCase(separate));

        Set<String> set = new HashSet<>();
        set.add(literalA);
        set.add(separate);
        System.out.println("set size: " + set.size());

        Map<String, Integer> values = new HashMap<>();
        values.put(new String("ticket-17"), 42);
        System.out.println("map lookup: " + values.get(new String("ticket-17")));

        StringBuilder builder = new StringBuilder("java");
        System.out.println("builder equals: " + literalA.equals(builder));
        System.out.println("builder content: " + literalA.contentEquals(builder));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicode equals: " + composed.equals(decomposed));
        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("normalized equals: " + composed.equals(normalized));

        System.out.println("same hash: "
                + ("FB".hashCode() == "Ea".hashCode()));
        System.out.println("same content: " + "FB".equals("Ea"));
    }
}
```

Compile and run:

```bash
javac --release 17 StringEqualityDemo.java
java StringEqualityDemo
```

Stdout:

```text
literal identity: true
separate identity: false
alias identity: true
content equal: true
case sensitive: false
ignore case: true
set size: 1
map lookup: 42
builder equals: false
builder content: true
unicode equals: false
normalized equals: true
same hash: true
same content: false
```

Explanation:

- **First three lines:** the two literals share an interned object; `new String` creates a separate object; `alias` is just a reference to the existing object.
- **`content equal`:** two different `String` objects are still equal in content. `equals` is case-sensitive while `equalsIgnoreCase` uses Java's case-ignoring rules.
- **`set size` and `map lookup`:** `HashSet` deduplicates and `HashMap` looks up keys based on content equality, without requiring the inputs to share the same reference.
- **`builder equals` and `builder content`:** `StringBuilder` is not a `String`. `String.equals(builder)` returns `false`; `String.contentEquals(builder)` can compare the content of a `CharSequence`.
- **Unicode:** precomposed `é` and `e` followed by a combining mark can look identical, yet contain different UTF-16 sequences; normalizing to NFC before comparing makes them equivalent.
- **Hash:** `"FB"` and `"Ea"` have the same hash code under `String.hashCode`, yet `equals` is still `false`. Do not infer content equality from hash codes alone.

## 5. `String.equals` and `hashCode` in collections

`String` implements both `equals` and `hashCode`. Java's general contract requires that when `a.equals(b)` returns `true`, **`a.hashCode() == b.hashCode()`**. Because `String` objects are immutable, the data used to compute the hash does not change. This is one of the foundations that makes strings work reliably as hash keys.

When a `HashMap` holds the key `new String("A-001")`, calling `get(new String("A-001"))` still retrieves the stored value because the two keys have the same content and the same hash. `HashSet` likewise deduplicates according to equality, even when two values are created through two separate `new` calls.

However, **having the same hash does not prove equality**. Collisions can happen, as in the `"FB"` and `"Ea"` example. The hash helps locate the lookup bucket; equality distinguishes the specific keys. Never replace `a.equals(b)` with a `hashCode` comparison because the result can be wrong.

Conversely, using `==` to look up order IDs, cache keys, or API data can fail when a value has equal content but comes from a new object. The business question is usually **same code**, not **same reference address**.

## 6. `null`, related methods, and how to choose

### Avoiding `NullPointerException`

If `input` can be `null`, then `input.equals("ok")` will throw a `NullPointerException` because a method cannot be invoked on a `null` reference. Two common approaches:

```java
String input = null;
boolean a = "ok".equals(input);                   // false
boolean b = java.util.Objects.equals(input, "ok"); // false
boolean c = java.util.Objects.equals(null, null);  // true
```

This is an **illustrative code snippet**. `"ok".equals(input)` is safe because the target object always exists. `Objects.equals(a,b)` handles both operands potentially being null and returns `true` if both are null. Therefore, check whether business requirements consider "two unknown values" to be equal.

### Other comparison operations

| API | Characteristics | When to use |
| --- | --- | --- |
| `a == b` | Compares for same reference | Checking identity or null |
| `a.equals(b)` | Compares exact content of two `String`s | Default string value comparison |
| `Objects.equals(a,b)` | Null-safe equality check; uses `equals` when values are present | Either side may be null |
| `a.equalsIgnoreCase(b)` | Ignores case differences per Java's rules, locale-independent | When requirements only need equivalence under those rules |
| `a.contentEquals(cs)` | Compares `String` content against a `CharSequence` | Comparing with `StringBuilder`, `StringBuffer`, etc. when appropriate |
| `a.compareTo(b)` | Lexicographical comparison by UTF-16 code units; returns 0 if strings have identical content | Natural ordering of `String` |
| `Collator` | Compares according to a locale's rules and strength level | Language-sensitive text sorting |

**`equalsIgnoreCase` is not universal text normalization.** It does not automatically trim whitespace, normalize Unicode, or guarantee the collation rules of every language. If you want to compare person names for ordering/equivalence by locale, consider `Collator` and dedicated data rules. For passwords, tokens, or signatures, do not automatically ignore character differences unless the protocol requires it.

A common point of confusion: `StringBuilder` inherits `Object.equals` with identity semantics, so two `StringBuilder`s containing the same characters are not equal by default. To compare content with a `String`, use `contentEquals` or convert the builder to a `String` and then use `equals`.

## 7. Unicode: looking alike does not guarantee `equals`

Text can have multiple Unicode representations. For example, the character `é` can be the precomposed character U+00E9 or the letter `e` U+0065 followed by the combining mark U+0301. The two forms may render almost identically, but `String.equals` compares **UTF-16 code units**, so it still sees a difference.

`String.length()` counts UTF-16 code units, not necessarily the number of characters perceived by a reader or the number of Unicode code points. Characters outside the BMP can consist of a surrogate pair, and accented letters with combining marks can span multiple code points. Therefore, exact content comparison is not the same as visual comparison.

When business logic wants two Unicode representations to be treated as equivalent, you can normalize them to the same form, such as NFC:

```java
import java.text.Normalizer;

String normalizedA = Normalizer.normalize(inputA, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(inputB, Normalizer.Form.NFC);
boolean same = normalizedA.equals(normalizedB);
```

This is an **illustrative code snippet**, assuming `inputA` and `inputB` already have values. NFC normalization handles Unicode canonical equivalence; it **does not automatically resolve all differences** in letter case, whitespace, lookalike characters from different alphabets, or Vietnamese-specific collation requirements.

For data keys and identifiers, establish the normalization policy **before writing and querying**, so every party uses the same interpretation. For passwords or security tokens, follow the protocol policy; do not apply normalization or ignore case on your own if doing so alters the expected secret.

## 8. Common mistakes in practice

**Mistake: using `==` for text received from outside.** Two different references can have the same content; compare using `equals` or a clearly defined normalization rule.

**Mistake: calling `equals` on a potentially null variable.** If comparing against a constant string, use `"constant".equals(value)`; if both variables may be null, use `Objects.equals` when treating two nulls as equal fits the business logic.

**Mistake: mistaking String Pool behavior for a general rule.** Two equal literals may share the same object, but runtime-concatenated data or data read from an API does not necessarily behave that way. Tests should include two `new String("same")` instances to observe `== false` and `equals true`.

**Mistake: assuming `equals` ignores case or whitespace.** `"Java".equals("java")` and `"x".equals("x ")` are both `false`. If whitespace removal or case transformation is needed, apply `strip()` or controlled casing with `Locale.ROOT`/the appropriate locale; keep in mind that case rules can be complex with Unicode.

**Mistake: assuming identical visual rendering means equal strings.** Combining marks and different normalization forms can cause `equals` to return false. Test with realistic Unicode characters from your data domain, especially names, multilingual text, and strings copied from multiple sources.

**Mistake: checking hashes instead of equality.** Two colliding hashes do not mean two strings have the same content. `HashMap`/`HashSet` handle collisions through the equals/hashCode contract; application logic also needs to check true value equality.

## 9. Checklist for retention and self-testing

1. Identify whether you are asking **same object** (`==`) or **same `String` content** (`equals`).
2. Create two strings with the same content via `new String` to demonstrate that identity can differ.
3. Compare literals, empty strings, uppercase/lowercase, spaces, `null` values, and Unicode text.
4. Verify that `HashSet` merges two equal strings and that `HashMap` can look up entries using a `String` key with a different reference.
5. Remember that `String.equals` only returns true for a `String` argument with identical UTF-16 content.
6. For potentially null values, choose `"literal".equals(variable)` or `Objects.equals` according to requirements.
7. Never use `StringBuilder.equals` or hash code comparisons as a substitute for content checks.
8. If case-insensitivity, Unicode normalization, whitespace trimming, or locale-aware comparison is required, define and apply explicit rules.
9. Confirm that the comparison serves the right **business identity** concept: two identical strings do not necessarily represent the same entity.

**Key takeaway:** `String.equals(Object)` compares exact text content according to Java `String` semantics, independent of whether two variables share the same reference. `==` checks identity; the String Pool merely explains why `==` sometimes returns `true` for two identical literals. When broader equivalence rules are needed, explicitly define normalization and comparison outside `String.equals`.
