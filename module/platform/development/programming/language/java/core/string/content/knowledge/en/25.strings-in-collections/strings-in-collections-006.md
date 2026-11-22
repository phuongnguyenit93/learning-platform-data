# Key Normalization vs. Preserving Display Text in Java Collections

## 1. The Problem: Same Search, Different Presentation

Suppose an application stores a product name, content tag, or dictionary entry in `Map<String, ...>`. A user enters `"  Café  "`, and later searches with `"café"`, `"CAFÉ"`, or the Unicode string `"Cafe\u0301"` (the letter `e` followed by a combining acute accent). The application may want all of those lookups to point to **the same entry**, yet when displaying it, preserve the exact name the user entered—including capitalization, accents, whitespace, or brand styling.

Those are two separate requirements:

- **Normalized/canonical lookup key**: a consistently defined representation used for comparison, searching, grouping, or duplicate detection.
- **Display text**: the original string or user-approved version used to render the intended meaning and appearance accurately.

**Never replace display text with the normalized key.** Normalization can discard information irreversibly: such as letter case, leading/trailing spaces, or certain character distinctions if the normalization policy is too aggressive.

The context of this lesson is **using `String` as keys in Java collections**, especially `HashMap`, `HashSet`, and `TreeMap`. Depending on the problem, not all data should be normalized: display names, usernames, product codes, identifiers, and passwords each have different policies.

## 2. `String.equals()` and Keys in `HashMap`

`String.equals()` compares string content by exact UTF-16 code units. `HashMap<String, V>` relies on the key's `hashCode()` and `equals()` when inserting or looking up entries; `HashMap` itself **does not automatically strip whitespace, lowercase text, or normalize Unicode**.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> prices = new HashMap<>();
prices.put("Café", 100);

System.out.println(prices.get("Café"));   // 100
System.out.println(prices.get("café"));   // null
System.out.println(prices.get("Cafe\u0301")); // null
```

`"Café"` in the first example contains a precomposed `é` character; `"Cafe\u0301"` contains `e` and a combining acute accent. They may look identical when rendered, yet they are not `equals()`. The lowercase string `"café"` also differs from `"Café"`.

Similarly, `HashSet<String>` can retain multiple visually identical strings because each remains a distinct element under `equals()`. To treat variants as the same key, you must **define and apply a normalization rule** before interacting with the collection.

## 3. Normalization Layers: Choose According to Need

### 3.1. Leading and Trailing Whitespace

`String.strip()` (Java 11+) removes leading and trailing characters that `Character.isWhitespace` classifies as whitespace. `trim()` uses an older criterion (`char <= U+0020`), so the two methods are not equivalent for all Unicode characters.

```java
String raw = "  Java  ";
String keyPart = raw.strip();

System.out.println(raw.length());     // 8
System.out.println(keyPart.length()); // 4
```

Not every kind of Unicode space is stripped by `strip()`; for example, a non-breaking space (`U+00A0`) needs its own policy if your data treats it as boundary whitespace. Avoid automatically deleting **all** spaces inside a string because `"New York"` and `"NewYork"` may carry different meanings.

### 3.2. Letter Case

For lookup keys requiring consistent behavior, `toLowerCase(Locale.ROOT)` is usually preferable to `toLowerCase()`, because the no-argument version uses the runtime's default locale and can change results across environments.

```java
import java.util.Locale;

String keyPart = "JAVA".toLowerCase(Locale.ROOT);
System.out.println(keyPart); // java
```

`Locale.ROOT` provides a uniform baseline rule, yet **lowercasing is not full Unicode case folding**. Do not assume that every pair of strings users treat as equivalent across languages becomes the same key. For example, handling `I/i`-related letters in Turkish follows language-specific rules. If an application needs linguistic matching, define and test the policy for that language.

### 3.3. Unicode Normalization: NFC and NFKC

`java.text.Normalizer` provides Unicode normalization forms, notably:

| Form | Typical meaning | When to consider |
| --- | --- | --- |
| `Normalizer.Form.NFC` | **Canonical equivalence** normalization preferring precomposed characters | Suitable when unifying canonically equivalent Unicode encodings while preserving meaningful distinctions |
| `Normalizer.Form.NFD` | Canonical decomposition | Useful for certain accent-processing steps; not the default key form |
| `Normalizer.Form.NFKC` | **Compatibility equivalence** normalization followed by composition | Use only when business rules intentionally treat presentation forms or compatible characters as identical |
| `Normalizer.Form.NFKD` | Compatibility decomposition | For specialized purposes; can lose representation distinctions |

NFC unifies the two representations of `é`:

```java
import java.text.Normalizer;

String composed = "\u00E9";   // é: one code point
String decomposed = "e\u0301"; // e and combining acute accent

System.out.println(composed.equals(decomposed)); // false
System.out.println(
        Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC))
); // true
```

**NFC does not strip accents.** Under an NFC policy, `"cafe"` and `"café"` remain distinct. NFKC can merge additional compatibility representations (such as full-width characters with their ASCII counterparts), so it should not be assumed universally safe for proper names, identifiers, or user content.

Stripping diacritics completely is **a different policy**, which can cause unintended collisions between words or names with different meanings. Do not conflate that policy with NFC unless explicitly required.

## 4. An Intentional Key Normalization Function

The following example chooses a concrete policy for a catalog entry searched case-insensitively while accepting canonically equivalent Unicode:

1. Strip leading/trailing whitespace with `strip()`.
2. Convert to lowercase using `Locale.ROOT`.
3. Normalize to NFC **after** lowercasing, ensuring the final output is canonically composed.

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

static String keyOf(String input) {
    Objects.requireNonNull(input, "input");
    String stripped = input.strip();
    String lower = stripped.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
```

This is an **illustrative method snippet** placed inside a Java class. It is not a mandatory rule for all systems. Every system must decide for itself whether stripping whitespace, ignoring case, handling Unicode equivalence, or allowing empty keys is appropriate.

Several important properties:

- `keyOf("  Café ")` and `keyOf("cafe\u0301")` produce the same key under this policy.
- `keyOf("Cafe")` and `keyOf("Café")` are **different** because NFC does not remove accents.
- The function does not mutate `input` because `String` is immutable; it returns a representative string for use in data structures.
- `null` is not a valid key in this example: `Objects.requireNonNull` rejects it explicitly instead of producing an unintended sentinel key.
- After `strip()`, a string may become `""`. If an empty key is invalid for business rules, validate and reject it before storing.

You must **apply the exact same function** across writes, lookups, updates, and deletes. If you normalize only on `put` and forget on `get`, lookups will still fail.

## 5. Data Design: Store Keys and Display Text Separately

A simple model using `Map<String, Item>`:

```java
record Item(String displayName) {}

Map<String, Item> items = new HashMap<>();

String submittedName = "  Cafe\u0301  ";
String lookupKey = keyOf(submittedName);

items.put(lookupKey, new Item(submittedName));
Item found = items.get(keyOf("CAF\u00C9"));
```

In this example:

- **The `Map` key** is the result of `keyOf(submittedName)`; it is used for matching.
- **The `Item.displayName` value** holds the exact original `submittedName`, including the two spaces on each side and the decomposed Unicode form.
- For display, read `found.displayName()`, never using the `Map` key string as the label.
- If you want to trim spaces *in the UI*, define that requirement separately for display data; do not infer it from key normalization.

In a larger application, you might use `record Item(String id, String displayName, ...)` with a separate **stable ID**. The normalized string works well as a search or grouping index key; it should not necessarily serve as the object's permanent ID.

### When Multiple Inputs Map to the Same Key

For instance, `"  Café  "` and `"cafe\u0301"` share the same normalized key. If you use:

```java
items.put(keyOf(submittedName), new Item(submittedName));
```

across multiple insertions, a later insert can **overwrite the value** at the same key. `HashMap.put` returns the previous value (if any), yet ignoring the return value makes it easy to silently lose an older display label.

Clearer strategies include:

- **Keys must be unique:** use `putIfAbsent` or check for collisions in the storage layer and notify the user when the name already exists.
- **Multiple items may share a search key:** use `Map<String, List<Item>>` or an inverted index so one key returns multiple objects.
- **Items have their own ID:** store records by ID, while the normalized key maps to a list of IDs; the display name is not the sole identity source.

In multithreaded or database-backed systems, a check-then-write pattern **does not guarantee atomicity on its own**. `HashMap` is not thread-safe for concurrent updates. `putIfAbsent` on `HashMap` is useful in single-threaded code, not a replacement for database transactions/unique constraints or proper concurrent structures.

## 6. Compilable and Runnable Java 17+ Example

Create the file `KeyNormalizationDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class KeyNormalizationDemo {

    record Item(String displayName) {}

    static String keyOf(String input) {
        Objects.requireNonNull(input, "input");
        return Normalizer.normalize(
                input.strip().toLowerCase(Locale.ROOT),
                Normalizer.Form.NFC
        );
    }

    public static void main(String[] args) {
        // Cafe + combining acute accent; two spaces on each side.
        String original = "  Cafe\u0301  ";
        String query = "CAF\u00C9";

        Map<String, Item> items = new HashMap<>();
        items.put(keyOf(original), new Item(original));

        System.out.println(
                "Same key: " + keyOf(original).equals(keyOf(query))
        );
        System.out.println(
                "Found: " + (items.get(keyOf(query)) != null)
        );
        System.out.println(
                "Display preserved: "
                        + items.get(keyOf(query)).displayName().equals(original)
        );

        Item existing = items.putIfAbsent(
                keyOf(query), new Item(query)
        );
        System.out.println("Collision: " + (existing != null));
        System.out.println("Size: " + items.size());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 KeyNormalizationDemo.java
java KeyNormalizationDemo
```

Exact output:

```text
Same key: true
Found: true
Display preserved: true
Collision: true
Size: 1
```

**Why?** `original` has whitespace and decomposed Unicode; `query` is uppercase and uses a precomposed `É`. After `strip()`, `toLowerCase(Locale.ROOT)`, and `Normalizer.Form.NFC`, the two keys match. `Map.get` locates the entry from the normalized key, while `displayName` remains equal to the exact original string—unchanged in casing, whitespace, or Unicode form. `putIfAbsent` detects an existing item at that key and does not overwrite it, so the `Map` size stays `1`.

Here `record` is nested inside the class; this syntax works in Java 17+.

## 7. `HashSet`, `TreeMap`, and Comparators

### `HashSet<String>`

For a set that should treat variants as the same element, store **normalized keys**:

```java
Set<String> keys = new HashSet<>();
keys.add(keyOf("  Café "));
keys.add(keyOf("cafe\u0301"));

System.out.println(keys.size()); // 1
```

If user-entered labels must be displayed, do not pull elements directly from the `keys` set as display content. Store them in a separate structure or attach them to a data object.

### `TreeMap<String, V>` and `TreeSet<String>`

Tree-based collections use `compareTo` or a `Comparator` to determine **both ordering and when keys are considered equal** (when `compare(a,b) == 0`). This differs from the `equals/hashCode` mechanism of `HashMap/HashSet`.

Example:

```java
Map<String, Integer> sorted = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
sorted.put("Java", 1);
sorted.put("JAVA", 2);

System.out.println(sorted.size()); // 1
System.out.println(sorted.get("java")); // 2
```

That comparator compares case-insensitively according to Java's rules, yet **does not replace a complete normalization policy**: it does not strip boundary whitespace, and it does not guarantee canonical Unicode equivalence like NFC. Do not assume an arbitrary comparator on a `TreeMap` enforces the same key identity rule as a `HashMap` storing normalized keys.

If you want the exact same rule across collections, it is usually clearest to **store and compare the keys generated by `keyOf` directly**. When designing a custom comparator, ensure consistency, reflexivity, and transitivity of the ordering relation; a comparator treating two keys as equal causes the collection to keep only one of the entries.

## 8. When Not to Normalize Keys This Way

The `keyOf` definition above fits the **catalog name search** example; it is not a universal rule for every `String`.

| Data | Approach to consider |
| --- | --- |
| Display labels, brand names, work titles | Preserve the accepted content; if search is needed, store an additional index key |
| Case-sensitive identifiers, secret tokens, signatures, byte-exact data | Do not auto-strip spaces, lowercase, or normalize Unicode; follow the exact system specification |
| Usernames defined by the product as case-insensitive | Establish the policy at account creation; apply at registration, login, renaming, and duplicate checks |
| Accent-insensitive Vietnamese search | Requires an explicit spec for diacritic removal, `đ`, whitespace normalization, and collision handling; NFC alone does not strip accents |
| Natural-language search | Consider a locale-appropriate `Collator`, full-text search, or dedicated index; do not assume lowercasing is always right |
| Unicode data with visually similar characters | NFC does not solve all visual confusables; add appropriate checks if that poses a business risk |

**Beware of lossy normalization.** `strip()` discards leading/trailing whitespace; `toLowerCase(Locale.ROOT)` drops case distinctions; `NFKC` and diacritic removal merge even more distinct inputs. If two business-distinct items fall onto the same key, collisions must be handled intentionally rather than silently overwriting or merging records.

In particular, decide the policy **before real data accumulates**. If you later change the normalization function, old keys in memory, files, caches, or databases may no longer match new keys. Plan re-indexing and collision resolution for migrations; for long-lived storage systems, you can record the policy version to support safe transitions.

## 9. Common Mistakes

1. **Normalizing only on write.** Calling `map.put(keyOf(name), item)` but `map.get(userInput)` causes variants not to be found. Always use `map.get(keyOf(userInput))`.
2. **Using the key as display text.** A user-entered label like `"  Cafe\u0301  "` turns into `"café"` if you display the key. Store the original label in the value or a separate field.
3. **Treating `equalsIgnoreCase` or `CASE_INSENSITIVE_ORDER` as Unicode normalization.** They address a different part of the problem; Unicode form, whitespace, and locale still need explicit rules.
4. **Calling `toLowerCase()` by default.** The default locale can vary by machine or runtime. For a locale-independent key policy, pass `Locale.ROOT`.
5. **Treating `NFKC`, diacritic removal, and NFC as identical.** They transform different scopes of characters; broader normalization can collapse distinct proper names or codes into the same key.
6. **Silently overwriting when two labels share a key.** If uniqueness is not guaranteed, keep a list of items or report collisions explicitly.
7. **Using a normalized display name as a permanent ID.** Names can change and normalization policies can evolve. Long-lived records usually need an independent, stable ID.
8. **Changing policy without migrating data.** Keys in caches/databases computed under old rules can cause missed lookups or duplicates after an upgrade.

## 10. Self-Check

**Question 1.** With `keyOf` above, does `keyOf("Cafe")` equal `keyOf("Café")`?

**Answer:** No. NFC unifies canonically equivalent character forms, but it does not strip the acute accent from `é`.

**Question 2.** Why is storing `Map<String, Item>` usually better than storing only a `Set<String>` of normalized keys when the application must display the original text?

**Answer:** `Map` keeps the key for lookup and a separate value carrying the display label. Storing only normalized keys loses the information needed to recover letter case, whitespace, or other stripped distinctions.

**Question 3.** Two names `"Café"` and `"cafe\u0301"` collide after normalization. Should `put` be used so the second overwrites the first?

**Answer:** Only when business rules intentionally allow replacement. If uniqueness is required, report a duplicate; if multiple items are allowed, store multiple values under one key; if IDs are needed, give each record a stable ID.

**Question 4.** Should passwords be normalized with `strip().toLowerCase(Locale.ROOT)` as in this lesson?

**Answer:** Do not apply this automatically. Passwords/tokens must follow the authentication mechanism's exact input rules; extra transformations can alter secret semantics and verification behavior.

## Remember

**A normalized key defines "when strings are considered the same"; display text preserves "how the user expects to see the string."** For `String` in collections, define a business-appropriate `keyOf` function, apply it consistently across all read/write paths, handle collisions explicitly, and store display labels separately when preservation is required.
