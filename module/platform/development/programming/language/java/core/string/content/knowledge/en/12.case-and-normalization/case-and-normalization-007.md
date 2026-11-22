# Distinguishing Unicode Normalization from Accent Stripping in Java

## 1. Two different operations, even though they often appear together

In Java, a `String` is a sequence of UTF-16 code units. Visually identical text can be represented by different code point sequences; for example, the letter **é** can be:

- Precomposed form: `U+00E9` (character `é`, one code point).
- Decomposed form: `U+0065 U+0301` (letter `e` and combining acute accent, two code points).

**Unicode normalization** converts text into one of the Unicode-defined representation forms so equivalent representations are handled consistently. For example, NFC turns `e + U+0301` into `é` when an eligible composed form exists; NFD converts back to `e + U+0301`. **The acute accent remains** in both cases.

**Accent/diacritic stripping** is an application-level transformation policy, typically used to build search keys or near-ASCII representations: `café` becomes `cafe`, `Cà phê` becomes `Ca phe`. This step **alters textual information** and can make words with different meanings identical. Standard Unicode normalization is **not synonymous** with stripping accents.

Three questions must be kept separate:
1. **Do you need to unify equivalent Unicode representations?** Use `java.text.Normalizer` with NFC/NFD (or NFKC/NFKD if compatibility equivalence is intended).
2. **Do you need to strip tone marks or diacritics for search?** Explicitly define which marks are removed, which scripts apply, and how non-decomposing characters are handled.
3. **Do you need language-aware comparison/sorting for users?** Look at `java.text.Collator` with the appropriate `Locale`; do not substitute arbitrary accent stripping.

## 2. Distinguishing characters, code points, UTF-16 units, and combining marks

`String.length()` counts **UTF-16 code units** (`char`), not the number of characters a user perceives. `String.codePointCount(begin,end)` counts Unicode code points within a UTF-16 range. A *grapheme cluster* can consist of a base character plus multiple combining marks or a complex emoji sequence.

Example:

```text
Display:                   é        é
Representation:           U+00E9    U+0065 U+0301
Code points:                1        2
UTF-16 chars:               1        2
NFC normalization:        U+00E9   → U+00E9
NFD normalization:   U+0065 U+0301 ← U+00E9
Strip marks after NFD:     "e"      "e"
```

`U+0301` is a combining mark belonging to the *Unicode Mark* category. Conversely, not every character that "looks accented" decomposes into a base Latin letter under NFD. The Vietnamese letters `đ` (`U+0111`) and `Đ` (`U+0110`) are an important example: NFD normalization **does not** turn them into `d`/`D`.

Characters outside the BMP (such as some emojis) take **two** `char`s and yet do not represent "two visible characters." Do not strip accents by iterating with `charAt` and guessing from glyph shapes; understand the Unicode data and the problem's rules.

## 3. NFC/NFD preserve accents; accent stripping requires a separate step

`Normalizer.normalize(text, Normalizer.Form.NFC)` puts a string into composed form when possible, while `NFD` puts it into decomposed form. **Both preserve accents.** `NFKC/NFKD` also consider compatibility equivalence, yet they themselves are not accent-deletion operations either. The dedicated lesson on `Normalizer` presents the complete table of all four forms.

## 4. Testing canonical equivalence comparison

```java
String a = "Caf\u00E9";
String b = "Cafe\u0301";
String nfc = java.text.Normalizer.normalize(b, java.text.Normalizer.Form.NFC);
String nfd = java.text.Normalizer.normalize(a, java.text.Normalizer.Form.NFD);
System.out.println(a.equals(b));         // false
System.out.println(nfc.equals(a));       // true
System.out.println(nfd.equals(b));       // true
System.out.println(nfd.equals("Cafe"));  // false: accent is still present
```

This is a snippet placed inside a method. Normalizing both sides to the same form enables canonical equivalence comparison, but matching `"Cafe"` from `"Café"` under an **accent-stripping policy** still requires an independent filtering step.

## 5. Stripping accents: a separate transformation after decomposition

A common way to build a **diacritic-stripped Latin search key** is:
1. Convert the string to `Normalizer.Form.NFD` so characters with **canonical decomposition** split into base characters and combining marks.
2. Remove code points in the Unicode `Mark` category according to a defined rule, such as Java regex `\p{M}+`.
3. If the product requires it, explicitly map **non-decomposing** characters such as `đ → d`, `Đ → D`.

Example snippet:

```java
String text = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
String decomposed = Normalizer.normalize(
        text, Normalizer.Form.NFD);
String withoutMarks = decomposed.replaceAll("\\p{M}+", "");
String asciiLike = withoutMarks
        .replace('\u0111', 'd')
        .replace('\u0110', 'D');
```

The result of `withoutMarks` is **`Ca phe sua đa`**, because `đ` remains intact. `asciiLike` has the content **`Ca phe sua da`** after the `đ` mapping rule. These are **transformed results**, no longer canonically equivalent to the original text.

In Java regex:
- `\p{M}` is the Unicode general category **Mark**: including *Nonspacing Mark* (`Mn`), *Spacing Combining Mark* (`Mc`), and *Enclosing Mark* (`Me`).
- `+` matches one or more consecutive `Mark` elements.
- In a **Java string literal**, you must write `"\\p{M}+"` (two backslashes in Java code) to pass the actual regex `\p{M}+` to `replaceAll`.
- `replaceAll` takes a **regex**, not a literal string; replacing with `""` deletes matched regions.

`\p{M}` covers more Unicode marks than just the `\p{InCombiningDiacriticalMarks}` block (U+0300..U+036F). However, that broad scope also means **risking deletion of essential marks in other scripts**. Do not treat it as a "safe Vietnamese accent remover for every language."

### Runnable program: two-step Vietnamese key builder

Save as `VietnameseAccentDemo.java`:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class VietnameseAccentDemo {
    private static final Pattern MARKS =
            Pattern.compile("\\p{M}+");

    static String removeMarks(String input) {
        String nfd = Normalizer.normalize(
                input, Normalizer.Form.NFD);
        return MARKS.matcher(nfd).replaceAll("");
    }

    static String vietnameseSearchKey(String input) {
        return removeMarks(input)
                .replace('\u0111', 'd')
                .replace('\u0110', 'D');
    }

    public static void main(String[] args) {
        String phrase = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
        String name = "\u0110\u1EB7ng";

        System.out.println(removeMarks(phrase));
        System.out.println(vietnameseSearchKey(phrase));
        System.out.println(removeMarks(name));
        System.out.println(vietnameseSearchKey(name));

        String bothWays = "Caf\u00E9 / Cafe\u0301";
        System.out.println(removeMarks(bothWays));
    }
}
```

```bash
javac -encoding UTF-8 VietnameseAccentDemo.java
java VietnameseAccentDemo
```

```text
Ca phe sua đa
Ca phe sua da
Đang
Dang
Cafe / Cafe
```

The `removeMarks` method demonstrates **removing Marks after NFD**. `vietnameseSearchKey` adds the **đ/Đ** option for Latin/Vietnamese key generation. Both methods return a new `String` value; the immutable input is untouched.

`removeMarks` does not mean "preserving full Vietnamese meaning": `"ma"`, `"má"`, `"mà"`, `"mã"`, `"mạ"` can collapse into the same string. Therefore, the accent-stripped version should be an **auxiliary search value**, never replacing the original string stored in the database or displayed to users by default.

## 6. Normalization does *not* remove accents; stripping accents is *not* canonical normalization

Consider three strings:

```text
A = "é"                 (U+00E9)
B = "e" + U+0301         (U+0065 U+0301)
C = "e"                 (U+0065)
```

`A` and `B` are **canonically equivalent**. NFC turns both into the same `é` representation; NFD turns both into `e + acute accent`. String `C` is not canonically equivalent to `A` or `B`: it lacks accent information.

If you write:

```java
String a = "\u00E9";
String b = "e\u0301";
String c = "e";

System.out.println(Normalizer.normalize(
        a, Normalizer.Form.NFC).equals(
        Normalizer.normalize(b, Normalizer.Form.NFC))); // true

System.out.println(Normalizer.normalize(
        a, Normalizer.Form.NFC).equals(c)); // false
```

This snippet requires `import java.text.Normalizer;` and goes inside `main`. This very difference between `A/B` and `C` explains why "normalize Unicode" **is not** "convert to unaccented text."

Accent stripping can create **information collisions**: distinct strings collapse into the same key. If accented words or names are the original data, stripping accents before storing without keeping the original causes irreversible information loss.

## 7. Do not confuse compatibility normalization with accent stripping

`NFKC/NFKD` can turn `ﬃ` (`U+FB03`) into `ffi`, `①` into `1`, and `Ａ` into `A`. Those examples are **not accent stripping**. Conversely, a Vietnamese letter with a tone mark still retains its mark information under NFKD unless some special compatibility rule applies. Do not use `NFKD` hoping it will produce ASCII; choose `NFD` before the `Mark`-filtering step when your Latin/Vietnamese search policy allows it.

## 8. Differences among `Normalizer`, `toLowerCase`, and `Collator`

These three operations relate to text yet have **different purposes**:

| Task | Typical API | Meaning |
| --- | --- | --- |
| Unify equivalent Unicode representations | `Normalizer.normalize(text, NFC)` | Normalizes representation form; preserves accented vs. unaccented distinction |
| Strip accents per application policy | NFD then filter `Mark`, optional `đ/Đ` mapping | Creates lossy data without accent information |
| Convert uppercase/lowercase | `toLowerCase(Locale.ROOT)` or a defined locale | Transforms case per Java/locale rules; **does not remove accents** |
| Language-aware comparison | `Collator.getInstance(locale)` | Compares/sorts by language rules, with configurable strength levels |
| Code-unit equality after normalization | `normalize(a, NFC).equals(normalize(b, NFC))` | Tests equality under the chosen canonical representation |

`String.toLowerCase()` depends on the default locale. To generate search keys independent of system language, you can pass `Locale.ROOT` explicitly, but you must verify business requirements: for languages like Turkish, casing rules and user expectations differ from neutral rules.

`Collator` supports locale-sensitive comparison; it has *strength* levels such as PRIMARY, SECONDARY, and TERTIARY. In many locales, PRIMARY treats certain accent and case differences as equal, yet **do not equate** it with deleting `\p{M}`. Actual behavior depends on the locale, collation data version, and language rules. `Collator.compare(a,b) == 0` only states that two strings are equivalent at the configured level, not that the original string lost its accents or had its content altered.

For systems with a search box, it is usually best to preserve the original text for display and build a separate search index/key per an explicit specification.

## 9. Why can deleting `\p{M}` break non-Latin scripts?

Unicode `Mark` is not limited to Vietnamese acute, grave, hook, tilde, and dot-below marks. Many scripts use vowel signs, diacritics, or combining symbols that are **essential structural parts of letters**.

For example:
- In several Indic scripts, vowel signs belong to `Mark`. Deleting all `\p{M}` can alter pronunciation and word meaning.
- Arabic includes vowel diacritics (*harakat*) that are marks; removing them may fit certain search tasks, but it is a linguistic choice rather than canonical normalization.
- Emoji variation selectors can fall under mark categories. Deleting them can switch emoji vs. text presentation for the same symbol, even without touching accented Latin letters.
- Some combining marks lie outside the `U+0300..U+036F` block; a regex targeting only that block can miss marks elsewhere in Unicode.

Therefore, `replaceAll("\\p{M}+", "")` should only appear in a **clearly named application helper** (e.g., `latinSearchKey`), after verifying the language set and data types where losing diacritics is permitted. If the application handles multilingual text, consider language-specific analyzers, Unicode collation, defined transliteration rules, or building auxiliary keys only for a scoped subset of data.

### `đ/Đ` and transliteration exceptions

`đ` is a distinct letter, not a `d` with a combining mark that NFD can detach. Characters like `ø`, `ł`, or `æ` also do not always decompose into the desired ASCII letters under NFD. **Transliteration** to ASCII is a separate policy that may require language-specific mapping tables.

Never claim that "NFD + strip Mark = ASCII": the output can still contain non-ASCII Unicode characters. Even after adding `đ → d`, input of unknown language may still require additional rules.

## 10. Storage and search: keep original data, build auxiliary keys when needed

A simple, semantically safe design:

```text
Input data
    │
    ├── Display value: keep user-entered text unchanged
    │
    ├── Canonical value (per policy): normalize NFC
    │
    └── Search key (per need):
           NFD → strip Marks per rule → map đ/Đ
           → apply case conversion per separate policy if needed
```

Using an auxiliary key lets `"ca phe"` match `"cà phê"` in an intentional search experience without replacing stored/displayed content with accent-stripped text. If you use the stripped key as a unique database key, `"ma"`, `"má"`, `"mạ"`, and `"mà"` can collide unintentionally.

Standalone example, save as `SearchKeyDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class SearchKeyDemo {
    private static final Pattern MARKS =
            Pattern.compile("\\p{M}+");

    static String searchKey(String value) {
        String canonical = Normalizer.normalize(
                value, Normalizer.Form.NFD);
        String noMarks = MARKS.matcher(canonical).replaceAll("");
        return noMarks.replace('\u0111', 'd')
                .replace('\u0110', 'D')
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String displayed = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
        String typed = "ca phe sua da";

        System.out.println(displayed);
        System.out.println(searchKey(displayed));
        System.out.println(searchKey(displayed).equals(searchKey(typed)));
        System.out.println(displayed.equals(typed));
    }
}
```

```bash
javac -encoding UTF-8 SearchKeyDemo.java
java SearchKeyDemo
```

```text
Cà phê sữa đá
ca phe sua da
true
false
```

The `searchKey` function fits only this **illustrative policy for Latin/Vietnamese data**. It produces a secondary string for fuzzy lookup and does not provide a security algorithm, identifier normalization, general transliteration, or semantic equivalence across all languages.

If results are used for password verification, signatures, legal identifiers, filenames, access permissions, or system-code matching, follow canonicalization rules matching **that domain's specification**. Do not arbitrarily apply compatibility normalization or accent stripping and treat two identifiers as equal.

## 11. Correctness, performance, and consistency

- **Define normalization boundaries**: if a system normalizes to NFC before writing while queries are not normalized the same way, exact comparisons can still miss matches.
- **Keep original data when stripping accents**: accent stripping is many-to-one; you cannot reliably reconstruct Vietnamese diacritics from `ca phe sua da`.
- **Do not use `String.length()` to count visible letters**: normalization can change the number of code points and UTF-16 code units while keeping visually canonically equivalent text.
- **Mind operation order**: normalize to NFD before removing Marks. If you strip Marks directly from precomposed `"café"`, `\p{M}` does not match `é` (which is a Letter), so the accent remains.
- **Do not assume all output is ASCII-only**: because NFD does not decompose every letter into basic Latin.
- **Limit allocations in hot loops**: normalization, regex, and case conversion all do processing work and can allocate new strings; for repeated queries, consider computing keys at ingestion or indexing time under one consistent policy.
- **Performance does not override specification**: do not optimize by discarding accents, encodings, or comparisons if business logic must distinguish those values.

One useful property: Unicode normalization is **idempotent** in content when applied repeatedly: `normalize(normalize(x, NFC), NFC)` equals `normalize(x, NFC)`. However, "idempotent" only means repeating normalization causes no further changes; it does **not** mean accents were stripped.

## 12. Common mistakes

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| `Normalizer.normalize(s, NFC)` strips accents | NFC reorganizes representation while **keeping accents** | Use a separate accent-stripping step if business logic requires it |
| NFD produces unaccented letters | NFD splits accents into combining code points; accents still exist | Decide explicitly whether to remove `Mark`s |
| `replaceAll("\\p{M}+", "")` works directly on any string | Precomposed accented letters like `é` are Letters, not separate Marks | Run NFD before removing Marks |
| NFD + strip Marks turns everything into ASCII | `đ` and many other letters do not decompose into ASCII characters | Add language-specific mappings or use a transliteration tool |
| Removing `\p{M}` is safe for all scripts | Marks can be core structural components of a script | Scope supported languages and target specifications |
| NFKD/NFKC are "just stronger NFD/NFC" without side effects | Compatibility normalization also transforms ligatures/circled digits/fullwidth forms | Use only when folding those variants is intended |
| Visually identical strings must satisfy `equals` | `String.equals` does not normalize Unicode | Normalize both sides to the same form before comparing |
| Accent stripping equals `Collator` comparison | Collation defines locale- and strength-based ordering/equivalence | Choose `Collator` for linguistic needs |
| Using stripped text as a unique key | Multiple accented words can collide onto the same key | Keep the original and design a collision policy |
| Using `toLowerCase()` without a locale for system keys | Result can depend on default locale | Choose `Locale.ROOT` or an explicit business locale |
| Counting code points as grapheme count | Combining marks and ZWJ emojis can build one visible glyph from many code points | Use grapheme segmentation when needed |

## 13. Exercises and answers

**Exercise 1.** Are `"Caf\u00E9"` and `"Cafe\u0301"` equal under `equals`? What happens after normalizing both to NFC?

**Exercise 2.** On `"C\u00E0 ph\u00EA"`, does NFD delete the accents or merely split them into separate code points? Which step is needed to obtain `"Ca phe"`?

**Exercise 3.** Why does NFD followed by removing `\p{M}` on `"Đặng"` produce `"Đang"` instead of `"Dang"`?

**Exercise 4.** Should you choose NFC or NFKC if you only need to unify canonical representations of user data and **do not want** `①` folded into `1`?

**Exercise 5.** When building accent-insensitive Vietnamese search, why must you store the original text and check for key collisions?

**Answers:**
1. Direct comparison is `false`; after NFC on both sides, it is `true`.
2. NFD **splits** the accents; then remove `Mark`s using a defined policy.
3. `Đ` is not decomposed into `D + Mark` by NFD; getting `Dang` requires an additional mapping `Đ → D`.
4. Use **NFC**, because `NFKC` performs compatibility transformations such as `① → 1`.
5. Because accent stripping loses information and distinct words can share the same key; the original is needed for display, preserving meaning, and distinguishing records.

## 14. Practical conclusion

**Unicode normalization** is an operation on **representation**: NFC/NFD bring canonically equivalent forms to the same representation while preserving the distinction between accented and unaccented letters. **Accent stripping** is a **content policy** operation: NFD can be used to separate marks before deleting `Mark`s and adding Vietnamese rules like `đ/Đ`, yet it is a lossy transformation and not the default output of `Normalizer`.

When accurate data is needed, keep original text and normalize canonically and consistently. When accent-insensitive search is needed, build a separate key with explicit language scope and rules. When linguistic comparison is needed, look at `Collator` instead of treating accent stripping as a universal Unicode comparator.

## Java SE 17 Documentation

- [`java.text.Normalizer` — NFC, NFD, NFKC, NFKD](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [`java.util.regex.Pattern` — Unicode categories and `\p{M}`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [`java.lang.String` — `equals`, `replaceAll`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`java.text.Collator` — comparison by locale and strength](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [`java.util.Locale` — locale rules for case conversion](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
