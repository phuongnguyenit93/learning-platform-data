# Length Changes After `String` Transformations and Their Impact on Old Indices

## 1. Objective

In Java, `String` is **immutable**: operations such as `replace()`, `toUpperCase()`, `strip()`, or Unicode normalization return a resulting string value rather than editing the old string object's content in place. **The resulting string can be longer or shorter than the original string**.

If you record the index of a character, token, or selection range from the original string and continue using it on the transformed string, that index may **point to the wrong character, slice the wrong range, or go out of bounds**.

Short example:

```java
import java.util.Locale;

String original = "Stra\u00DFe|END";          // Straße|END
int oldSeparator = original.indexOf('|'); // 6

String changed = original.toUpperCase(Locale.ROOT);
// "STRASSE|END": ß turns into SS; 1 extra char is added.

System.out.println(oldSeparator);              // 6
System.out.println(changed.indexOf('|'));       // 7
System.out.println(changed.charAt(oldSeparator)); // E
```

Index `6` is still valid within bounds, yet **no longer points to the `|` character**. This is more dangerous than an out-of-bounds index error, because the program can run without crashing while producing wrong results.

After this lesson, you will be able to:
- Distinguish `String.length()`, Unicode code point count, and displayed character count.
- Recognize transformations that can alter the number of UTF-16 code units.
- Understand index shifts when characters **before** a saved position are inserted, deleted, or expanded.
- Write code that re-locates boundaries on the transformed string and know when a deliberate position-mapping model is needed.
- Avoid confusing code point index conversion with position mapping **across two different string versions**.

## 2. Indices in `String` Are UTF-16 Indices

`String.length()` returns the number of **UTF-16 code units** (16-bit `char` units). APIs such as `charAt(index)`, `substring(begin, end)`, `indexOf(...)`, and positions returned by `Matcher.start()/end()` also use UTF-16 indices.

One Unicode code point can occupy **one or two `char`s**; one user-perceived character (*grapheme cluster*) can consist of multiple code points.

| String | `length()` (UTF-16 units) | Code point count | Why? |
| --- | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | Each ASCII letter needs one `char`. |
| `"A🚀B"` | 4 | 3 | `🚀` is a non-BMP code point, requiring two `char`s. |
| `"\u00E9"` (é) | 1 | 1 | Precomposed form U+00E9. |
| `"e\u0301"` (e + acute accent) | 2 | 2 | One visible letter can use two code points. |

Therefore, **"length change" must be understood by unit of measurement**. If a transformation turns one code point into two code points (`ß` → `SS`), `length()` increases by one. If a decomposed accented sequence is normalized into a precomposed character (`e` + acute accent → `é`), `length()` decreases by one. If `"A"` is replaced with `"🚀"`, the code point count remains one while `length()` increases from `1` to `2`.

## 3. Transformations That Can Change Length

| Transformation | Example | Possible effect |
| --- | --- | --- |
| `replace(CharSequence, CharSequence)` | `"abc".replace("b", "XYZ")` → `"aXYZc"` | A source segment can become a longer or shorter segment. |
| `replaceAll(regex, replacement)` | `"a  b".replaceAll(" +", " ")` → `"a b"` | Regex matches can change length; watch regex and replacement syntax. |
| `toUpperCase(Locale)` | `"Straße"` → `"STRASSE"` with `Locale.ROOT` | One character can map to multiple characters. |
| `toLowerCase(Locale)` | Certain Unicode variants or locale rules | Full-string conversion can produce a different number of code points. |
| `strip()`, `stripLeading()`, `stripTrailing()` | `"  Java  ".strip()` → `"Java"` | Removes matching code points at the edges. |
| `trim()` | `"  Java  ".trim()` → `"Java"` | Removes code units with value `<= U+0020` at the edges. |
| `Normalizer.normalize(..., NFC)` | `"e\u0301"` → `"\u00E9"` | Composes equivalent representations, potentially shortening. |
| `Normalizer.normalize(..., NFD)` | `"\u00E9"` → `"e\u0301"` | Decomposes characters, potentially lengthening. |
| `substring(begin, end)` | `"ABCDE".substring(1, 3)` → `"BC"` | Creates a string for a selected range; new indices start from `0`. |
| `repeat(int)` | `"AB".repeat(3)` → `"ABABAB"` | Length can grow according to repetition count. |

**Note:** The source `String` keeps its content unchanged, so old indices still have the same meaning **on the old source itself**. They become a problem when applied to the **new resulting string**.

A specific transformation sometimes leaves length unchanged. For example, `"java".toUpperCase(Locale.ROOT)` still has length 4. Never infer from a few simple examples that all case conversions preserve length.

## 4. Index Shift Mechanism: Inserting, Deleting, or Replacing Before an Index

Suppose in the original string you save a position `p`. A transformation occurs solely **before** that position, replacing a source segment of length `oldSize` UTF-16 code units with a new segment of length `newSize`. If the transformation is a single simple replacement and does not touch the target character itself, the new position is:

```text
newIndex = oldIndex + (newSize - oldSize)
```

Example source `"ABC|END"`, where the index of `|` is `3`:
- Replacing `"ABC"` with `"ABCDE"`: inserts two extra code units before `|`, so the new position is `5`.
- Replacing `"ABC"` with `"X"`: reduces by two code units, so the new position is `1`.
- Modifying a range **completely after** `|`: the position of `|` does not change, provided no other transformation occurs before it.

**The formula above only describes a single simple change with a known replacement range.** If multiple regions are replaced, the general rule is to sum the deltas of replacements occurring **before** the target position; if the transformation deletes, replaces, or reorders the target itself, a single new index cannot always be determined simply by adding an offset.

With Unicode normalization, context-dependent case mapping, regex processing, or multi-match replacements, simply "adding one global offset" is usually insufficient. You must re-locate positions on the output text or maintain a mapping table generated alongside the transformation.

## 5. Case 1: Uppercasing Can Expand `ß` to `SS`

On Java 17:

```java
String original = "Stra\u00DFe|END";
int oldPos = original.indexOf('|'); // 6

String upper = original.toUpperCase(java.util.Locale.ROOT);

System.out.println(original.length()); // 10
System.out.println(upper.length());    // 11
System.out.println(oldPos);            // 6
System.out.println(upper.indexOf('|'));// 7
System.out.println(upper.charAt(6));   // E
```

Index explanation:

| String | Content | Index of `|` |
| --- | --- | ---: |
| Original | `Straße|END` | 6 |
| After transformation | `STRASSE|END` | 7 |

The `"Straße"` portion is 6 code units long, while `"STRASSE"` is 7. Adding one code unit before `|` shifted every following position by one unit.

Points to note:
- `toUpperCase(Locale.ROOT)` performs uppercasing independent of the default locale, yet **does not guarantee preserving length**.
- `toLowerCase(Locale)` can also be locale-dependent, context-sensitive, and length-changing. For example, some transformations of `İ` (Latin capital I with dot) can produce multiple code points under an appropriate locale.
- Case conversion does not return a **source → result position map** to the caller; knowing only the resulting text is not enough to reconstruct every correspondence when characters expand or merge.

## 6. Case 2: Unicode Normalization Can Shorten or Lengthen

Unicode has multiple canonically equivalent encodings. The letter `é` can be:
- One precomposed code point `U+00E9`.
- Two code points `U+0065` (`e`) and `U+0301` (combining acute accent).

`Normalizer.Form.NFC` can compose them into one code point; `Normalizer.Form.NFD` can decompose them.

```java
import java.text.Normalizer;

String decomposed = "Cafe\u0301|OK";
int separatorBefore = decomposed.indexOf('|'); // 5

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(decomposed.length());     // 8
System.out.println(normalized.length());     // 7
System.out.println(separatorBefore);         // 5
System.out.println(normalized.indexOf('|'));  // 4
System.out.println(normalized.charAt(5));     // O
```

The `|` character at index 5 in the original string moves to index 4 in the NFC string. If you extract the portion after the separator using `substring(separatorBefore + 1)` on the normalized string, you will drop the first character of the desired substring.

**Normalization does not mean stripping diacritics**. NFC preserves canonical Unicode meaning; it only changes representation. `Normalizer.Form.NFKC/NFKD` additionally performs compatibility normalization, which can affect other character distinctions. Choose the normalization form based on data requirements and accept that length can change.

## 7. Case 3: Replacement and UTF-16 Length Change with Emojis

`String` uses UTF-16, so replacing a BMP character with a non-BMP code point can increase `length()` even when the code point count stays unchanged.

```java
String source = "A\uD83D\uDE80B"; // A🚀B
int oldB = source.indexOf("B");   // 3

String changed = source.replace("A", "AA");

System.out.println(source.length());  // 4
System.out.println(changed.length()); // 5
System.out.println(oldB);             // 3
System.out.println(changed.indexOf("B")); // 4
```

The `🚀` character itself occupies **two** code units, and the replacement inserts an extra `A` before `B`, so `B` shifts from index 3 to 4.

Another example, replacing `"A"` with `"🚀"`:

```java
String source = "AB";
String changed = source.replace("A", "\uD83D\uDE80");

System.out.println(source.length());          // 2
System.out.println(changed.length());         // 3
System.out.println(source.codePointCount(0, source.length()));   // 2
System.out.println(changed.codePointCount(0, changed.length())); // 2
```

Here **the code point count remains 2**, while UTF-16 length grows from 2 to 3. Therefore, looking only at before/after code point counts is insufficient for computing offsets for `char`-indexed APIs.

## 8. Standalone Java 17+ Program

Save the following content into `StringIndexAfterTransformDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class StringIndexAfterTransformDemo {
    public static void main(String[] args) {
        String original = "Stra\u00DFe|END";
        int oldSeparator = original.indexOf('|');
        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println("original = " + original);
        System.out.println("upper = " + upper);
        System.out.println("original length = " + original.length());
        System.out.println("upper length = " + upper.length());
        System.out.println("old separator = " + oldSeparator);
        System.out.println("new separator = " + upper.indexOf('|'));
        System.out.println("char at old index = "
                + upper.charAt(oldSeparator));
        System.out.println("correct right part = "
                + upper.substring(upper.indexOf('|') + 1));

        String decomposed = "Cafe\u0301|OK";
        String nfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFD-like length = "
                + decomposed.length());
        System.out.println("NFC length = " + nfc.length());
        System.out.println("old NFC separator = "
                + decomposed.indexOf('|'));
        System.out.println("new NFC separator = " + nfc.indexOf('|'));

        String emoji = "A\uD83D\uDE80B";
        String inserted = emoji.replace("A", "AA");

        System.out.println("emoji old length = " + emoji.length());
        System.out.println("emoji new length = " + inserted.length());
        System.out.println("emoji old B index = " + emoji.indexOf("B"));
        System.out.println("emoji new B index = " + inserted.indexOf("B"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringIndexAfterTransformDemo.java
java StringIndexAfterTransformDemo
```

Output:

```text
original = Straße|END
upper = STRASSE|END
original length = 10
upper length = 11
old separator = 6
new separator = 7
char at old index = E
correct right part = END
NFD-like length = 8
NFC length = 7
old NFC separator = 5
new NFC separator = 4
emoji old length = 4
emoji new length = 5
emoji old B index = 3
emoji new B index = 4
```

The old `String` instance was never modified. The pairs `original`/`upper`, `decomposed`/`nfc`, and `emoji`/`inserted` hold distinct versions of the content. Every index must be interpreted **against the exact string version that produced it**.

## 9. Common Mistake: Reusing `substring`, `Matcher`, or Old Cursor Positions

Suppose you split a string into two parts around `|`:

```java
String input = "Stra\u00DFe|END";
int cut = input.indexOf('|');

String upper = input.toUpperCase(java.util.Locale.ROOT);

// WRONG: cut was computed on input, not upper.
String wrong = upper.substring(cut + 1);

// RIGHT: find the boundary again on the resulting string.
int newCut = upper.indexOf('|');
String correct = upper.substring(newCut + 1);
```

In this example `wrong` returns `"|END"`, whereas `correct` returns `"END"`, because after expanding `ß`, the separator's position increased by 1.

Other places where this bug can appear:
- Saving `start`/`end` from `Matcher.find()` on the original string, then using those indices to slice after `replaceAll` or normalization.
- Saving a delimiter position via `indexOf`, then calling `stripLeading` which deletes the prefix.
- Saving a selection start position in an editor, then normalizing or replacing text before that selection.
- Saving a cut boundary based on original `length()`, then changing case on the entire string.
- Recording a UTF-16 index in one system and passing it as a code point index to another API.

**Rule:** An index does not exist in isolation; it always belongs to **a text version + an index unit + a positional meaning**.

## 10. Safe Ways to Handle It

### Approach A — Transform First, Find Indices Afterward

When boundaries can be identified by a delimiter, pattern, or token after transformation, process the string first and locate positions on the result itself:

```java
String normalized = java.text.Normalizer.normalize(
        input, java.text.Normalizer.Form.NFC);
int separator = normalized.indexOf('|');

if (separator < 0) {
    throw new IllegalArgumentException("Missing separator");
}
String right = normalized.substring(separator + 1);
```

This is simple, though you must check whether the transformation could alter or remove the delimiter. When a symbol or keyword appears multiple times, `indexOf` does not automatically tell which original occurrence you meant to track; use a more stable structure (an ID, syntax-tree token position, or offset map).

### Approach B — Extract Meaningful Regions First, Then Transform Each Region

When text parts are separated by a clear boundary, it is often cleaner to **split first**:

```java
import java.util.Locale;

String input = "Stra\u00DFe|END";
int separator = input.indexOf('|');

String left = input.substring(0, separator)
                   .toUpperCase(Locale.ROOT);
String right = input.substring(separator + 1)
                    .toUpperCase(Locale.ROOT);

String result = left + "|" + right;
System.out.println(result); // STRASSE|END
```

Here, the boundary is determined on the original string right where it is meaningful; subsequent transformations run independently inside each part. Of course, if you still need to point to characters inside `left` or `right` after transformation, positions inside that part must still be recomputed.

### Approach C — Position Mapping When You Control the Edits

If you deliberately perform **one** replacement of range `[start, end)` in the original string with `replacement`, you can compute the offset for positions located **after** the replaced range:

```java
int oldLength = end - start;
int newLength = replacement.length();
int delta = newLength - oldLength;

// Applies to a position p located AFTER or AT end,
// and only when this is the sole edit affecting before p.
int newPosition = p + delta;
```

If `p < start`, the position does not change (assuming no other edits). If `p` lies **inside** the replaced range, there is no universal rule for the "corresponding character" in the result; you must define a cursor policy (such as snapping to the start or end of the replaced segment) per application.

For multiple edits, construct a mapping from the sequence of edits performed: record each source range, target range, and cumulative offset. Non-one-to-one transformations, such as normalization or case mapping, need dedicated mapping rules for positions inside merged/expanded segments. Do not infer mappings using a global length ratio.

### Approach D — When Editing Multiple Original Ranges, Consider Right-to-Left Order

When you have multiple **non-overlapping ranges predetermined on the original string**, applying replacements from higher indices down to lower indices keeps the original positions **to the left** unshifted.

Example:

```java
StringBuilder text = new StringBuilder("abcd");

// Trailing range first, then leading range; the two ranges do not overlap.
text.replace(2, 4, "XYZ"); // abXYZ
text.replace(0, 2, "P");   // PXYZ

System.out.println(text); // PXYZ
```

This is a useful technique for multiple application-positioned edits; it **does not automatically map** cursors or tokens across a full-string Unicode normalization, and should not be applied indiscriminately when ranges overlap.

## 11. `offsetByCodePoints` Converts Units, Not Across Transformations

The `String.offsetByCodePoints(int index, int codePointOffset)` API takes a **UTF-16 index** within **one specific string**, moves by a number of code points, and returns a UTF-16 index within **that same string**.

Example:

```java
String text = "A\uD83D\uDE80B"; // A🚀B
int beforeRocket = text.offsetByCodePoints(0, 1);
int afterRocket = text.offsetByCodePoints(beforeRocket, 1);

System.out.println(beforeRocket); // 1
System.out.println(afterRocket);  // 3
System.out.println(text.substring(beforeRocket, afterRocket)); // 🚀
```

This method is very useful when slicing a string by code point count. However, if you have transformed `text` into another `String` whose length or content changed, you cannot pass old indices into the new string and assume they remain valid.

Some transformations can change **even the number of code points** (`ß` → `SS`, `e + ◌́` → `é`). Therefore, switching to code point indices **does not eliminate the need to map between the original version and the resulting version**.

## 12. Testing When an Application Stores Text Positions

For editing, highlighting, annotation, parsing, or data extraction features, you should test at least the following groups:

| Test data | What to verify |
| --- | --- |
| Simple ASCII, no length change | Indices remain accurate when the transformation truly preserves units and order. |
| Characters with case expansion like `ß` | Indices after the expanded region increase. |
| Strings with combining marks + NFC/NFD | Indices can shrink/grow; an old range may no longer correspond `char`-for-`char`. |
| Non-BMP characters like `🚀` | UTF-16 indices differ from code point counts. |
| Strings with leading whitespace + `stripLeading` | All positions after the removed prefix must be recomputed on the new string. |
| Multiple regex replacements changing length in many places | A single offset is usually insufficient; systematic recomputation/mapping is needed. |
| Delimiters or tokens replaced/deleted | Cannot simply re-find by the old literal; a token identification strategy is needed. |
| Indices inside a replaced range or right on a boundary | Anchor policy must be clearly defined. |

When persisting indices in an API or database, document the unit (**UTF-16 code unit**, **code point**, or **grapheme cluster**) and the text version that the position references. An index may still fall within valid bounds while representing an entirely different part of the string after transformation.

## 13. Common Mistakes

**Mistake 1 — "`String` is immutable so indices don't change."** The original object is immutable; the string after transformation is a different value. Old indices apply to the original object.

**Mistake 2 — "Case conversion always maps one character to one character."** Some Unicode mappings such as `ß` → `SS` change the number of code points and `char`s. Do not rely on this assumption for international text.

**Mistake 3 — "Unicode normalization does not change length."** NFC/NFD can compose/decompose code points, so boundary positions change even when text meaning is equivalent.

**Mistake 4 — "If code point count stays the same, UTF-16 indices stay the same."** Replacing `"A"` with `"🚀"` keeps one code point yet adds one UTF-16 code unit.

**Mistake 5 — "If `index < newString.length()`, it's safe to use."** Bounds checking only confirms an arithmetically valid position; it does not guarantee it still points to the old token/character.

**Mistake 6 — "Re-finding with `indexOf` always maps the original position accurately."** If a token appears multiple times, was altered, or was deleted during transformation, you need stable identifiers or a mapping built alongside the operation.

**Mistake 7 — "`offsetByCodePoints` converts an index from the old string to the new string."** This API only steps by code points **within the same string**.

## 14. Self-Check Exercises

### Exercise 1 — Separator Position After Case Mapping

```java
String a = "Stra\u00DFe|OK";
int p = a.indexOf('|');
String b = a.toUpperCase(java.util.Locale.ROOT);
```

What are `p` and `b.indexOf('|')`?

**Answer:** `p == 6`, `b.indexOf('|') == 7`. `"Straße"` turns into `"STRASSE"`, which is one UTF-16 code unit longer.

### Exercise 2 — Separator Position After NFC

```java
String a = "e\u0301|B";
String b = java.text.Normalizer.normalize(
        a, java.text.Normalizer.Form.NFC);
```

What position is `|` at before and after?

**Answer:** Before at index `2` (two code points: `e` and acute accent), after at index `1` (precomposed letter `é`).

### Exercise 3 — Code Point vs. UTF-16 Indices

```java
String before = "AB";
String after = before.replace("A", "\uD83D\uDE80");
```

What are `after.length()` and the code point count?

**Answer:** `after.length() == 3`, while `after.codePointCount(0, after.length()) == 2`. `🚀` is one code point but two `char`s.

### Exercise 4 — Fixing Stale Offset Usage

```java
String input = "Stra\u00DFe|END";
int oldPos = input.indexOf('|');
String upper = input.toUpperCase(java.util.Locale.ROOT);

// Need to extract "END", but the following code extracts wrongly:
String result = upper.substring(oldPos + 1);
```

**Fix:** Compute `int newPos = upper.indexOf('|');` and then `String result = upper.substring(newPos + 1);`. If multiple delimiters exist, identify the exact one needed to avoid picking the wrong occurrence.

### Exercise 5 — Can an Offset Always Be Updated Using the `length()` Difference?

**Answer:** Only under specific conditions: you know the edited ranges and they lie before the position to update without replacing or deleting that position itself. For multiple edited ranges or full-string Unicode transformations, you must track a mapping or re-locate positions on the result; global `newLength - oldLength` is not enough for arbitrary mapping.

## References

- [Java SE 17 — `String` API: `length`, `substring`, `replace`, `toUpperCase`, `offsetByCodePoints`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Normalizer`: NFC, NFD, NFKC, NFKD](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 17 — `Character`: Unicode code points and surrogates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
